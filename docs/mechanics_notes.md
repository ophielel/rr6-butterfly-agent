# 机制笔记（实现口径 / 公式 / 假设）

> 这份文档回答一个问题：**模拟器里的每一条规则是从哪来的、置信度多高、
> 如果和游戏不一致应该改哪里。**
>
> 数据侧来源见 `docs/sources.md`；待游戏内校验清单见 `docs/verification_checklist.md`。

## 0. 总体原则

计划书 §7 / §9 / §26：**规则正确性 > replay/测试 > 搜索基线 > 训练 > 性能**。

* 所有伤害都必须走「逐枚硬币」路径，不存在「先算总伤害再扣 HP」的捷径。
* 每次结算只通过事件时点触发：技能效果、状态钩子、被动都绑在同一个时点表上。
* 每一条不确定的数值/公式都是 `SimConfig` 字段或带 `confidence` 的数据字段，
  不允许散落在代码里。

## 1. 事件时点表

`rr6sim.core.enums.Timing`（引擎在 `Battle` 的固定位置触发）：

```
battle_start
turn_start            # 状态钩子、被动、Boss SP 回复
speed_roll            # 每个行动槽独立 roll 速度
skill_choices_ready   # 每个槽抽 2 个技能候选
（玩家/算法自回归构造本回合计划）
combat_start          # 计算行动顺序
  per 行动槽（速度降序）:
    on_use            # [使用时]（技能级 + E.G.O 被动 + 出血类状态）
    before_clash      # [拼点前]
    on_clash_win / on_clash_lose
    before_attack     # [攻击前]
      per 硬币:
        before_coin
        on_coin_heads / on_coin_tails
        on_hit        # [命中时]（技能硬币效果 → 目标状态钩子 → 攻击者被动）
        after_coin
    after_attack      # [攻击后]
    on_stagger / on_death
turn_end              # 状态衰减、幻影回补、形态判定
```

单枚硬币的结算顺序（`Battle.resolve_coin`，**这是最容易被写错的地方**）：

1. `before_coin`（硬币效果 + 技能效果）
2. `on_coin_heads` / `on_coin_tails`
3. `on_hit`：技能/硬币的 [命中时] 效果（先施加状态）
4. 伤害结算（`damage.deal`）→ 幻影处理 → 混乱 → 死亡 → 本体 HP 阈值
5. 目标身上的「命中时」状态钩子（沉沦 / 蝶 / 破裂 / 亡蝶…）
6. 攻击者身上的「命中时」状态钩子 + 攻击者被动
7. `after_coin`

> 「先施加状态再触发」是刻意的：沉沦队在同一枚硬币上「施加沉沦 → 立即触发」的
> 手感来自这里。若游戏实际是「触发后再施加」，把第 3 步与第 5 步交换即可。

## 2. 硬币 / 拼点

* 硬币威力：`value = base_power + (coin.power if 有利面 else 0)`
  * 正硬币：正面为有利面；负硬币：反面为有利面。
* 有利面概率：`P(正面) = clamp(0.5 + SP × san_per_point, 0.05, 0.95)`，
  正负硬币共用（负硬币在低 SP 时更容易吃到硬币威力 → 泪锋之剑 / 绝望类人格的手感）。
* 拼点模型（`SimConfig.clash_model`）：

  | 模型 | 规则 | 结果 |
  |---|---|---|
  | `advance`（默认） | 每轮双方各翻**下一枚**硬币，败者硬币被破坏，平手双方破坏 | 硬币数多的一方占优 |
  | `reflex` | 胜者保留当前硬币继续拼，只有败者硬币被破坏 | 高威力少硬币（单硬币 E.G.O）占优 |

  计划书没有规定拼点细节，两种社区理解都实现了，默认 `advance`；
  切换后 golden replay 会变化（这是预期行为，请重新生成 golden）。
* `clash_coin_carryover=true`：拼点胜利后，已翻出硬币的正反面结果沿用到伤害阶段。
* 拼点胜负的 SP 变化：`clash_win_sp_gain=+1`，`clash_lose_sp_loss=0`（待校验）。
* 行动顺序：速度降序 → 我方优先 → 单位/槽位顺序。
* 改目标：只有速度快于被保护槽位时才能改（`enforce_redirect_speed`）。

## 3. 伤害

```
伤害 = 硬币伤害
     × (1 + 0.03 × (攻击等级 - 防御等级))          # level_diff_damage_per_level
     × 物理抗性 × 罪孽抗性
     × 目标受到伤害倍率（脆弱/时隙/眩惑/影之龟裂/保护…）
     × 混乱倍率（1.5，处于混乱时）
     × 守备倍率（0.5）
     × 本次临时倍率（技能效果 / 造成伤害倍率（绝望…））
```

* `coin_power_adds_damage=true` 时，硬币伤害 = `coin.damage + (有利面时的 coin.power)`。
  这样精神力/硬币结果会同时影响拼点与伤害（更接近游戏手感）。
* 所有倍率都可在 `SimConfig` 调整；`DamageBreakdown` 会记录每一项，便于 replay 审计。

## 4. 状态

状态 = 强度(potency) + 层数(count)。实现的关键状态：

| key | 中文 | 触发 | 说明 |
|---|---|---|---|
| `sinking` | 沉沦 | `on_hit` | 失去等同强度的精神力，层数 -1；**强度会累积**，是重投 E.G.O 的触发条件 |
| `butterfly` | 蝶 | `on_hit` | 同时造成精神力与 HP 伤害（消融 G 可关闭特殊部分） |
| `dead_butterfly` | 亡蝶 | `on_hit` | 追加 HP 伤害，层数 -1 |
| `manor_echo` | 山庄的回响 | `turn_end` | 精神力伤害 = 层数 × 2 |
| `rupture` | 破裂 | `on_hit` | HP 伤害 = 强度，层数 -1 |
| `bleed` | 出血 | `on_use` | 使用攻击技能时 HP 伤害 = 强度，层数 -1 |
| `burn` | 燃烧 | `turn_end` | HP 伤害 = 强度，层数 -1 |
| `timegap` | 时隙 | — | 受到伤害 +5%/层，回合结束 -1 层（罗生蝶形态切换的易伤） |
| `fragile` | 脆弱 | — | 受到伤害 +5%/层 |
| `dazzle` / `shadow_crack` | 眩惑 / 影之龟裂 | — | 受到伤害 +5%/层 |
| `strong` / `offense_level_up/down` | 强壮 / 攻击等级升降 | — | 攻击等级 ±1/层 |
| `clash_power_up` | 拼点威力提升 | — | 拼点威力 +1/层 |
| `protect` / `blessing` | 保护 / 加护 | — | 受到伤害 -10%/层 |
| `despair` | 绝望 | — | 造成伤害 +10%/层 |
| `past` / `present` / `future` | 过去 / 现在 / 未来 | — | 罗生蝶三套状态栈（只有层数） |

触发器统一由 `data/statuses.json` 的 `hooks` 描述，`core/effects.py` 执行。

## 5. 罗生蝶（RR6 第五区段）

实现口径（全部来自 `data/boss_rr6_butterfly.json`，数值待校验）：

* 本体 + 三幻影（过去 / 现在 / 未来），各自有行动槽。
* 攻击幻影：**每枚硬币**削减对应状态栈 1 层（`phantom_stack_decay_per_coin`）。
* 幻影受到的伤害按 `phantom_damage_transfer`（默认 1.0）转移给本体。
* 幻影 HP 归零 → 破碎（不参与回补），`phantom_broken_turns` 回合后复原。
* 回合结束时，**整回合没有被作为主要目标**攻击的幻影 → 对应状态栈 +2
  （`phantom_restore_amount`）。
* 形态 = 三套栈中最高者（并列时保持当前形态，全 0 则 `neutral`）；
  形态变化时本体获得「时隙」层数（`form_switch_timegap`）。
* 本体 HP 跨过 `stack_thresholds`（按 HP 百分比记录）时三套栈 +2
  （`hp_threshold_stack_bonus`）。
* 本体有 4 个混乱阈值（按 HP 百分比记录）。
* 本体每回合开局回复 8 SP（`sp_recovery` 被动），避免沉沦一回合把它压死。
* RR6 前三段的「禁用被动」是配置项：被动效果带 `rr6_passive` 名字，
  出现在 `config.disabled_rr6_passives` 里就会被剔除。
* 第五区段事件增益通过 `config.encounter_buffs` 注入
  （`boss_hp_mult` / `initial_stacks` / `boss_extra_statuses` / `ally_extra_statuses` /
  `initial_form` / `phantom_acts`）。

## 6. 重投 / 追加硬币

* 「重复投掷」有两种粒度：
  * 硬币级：效果绑在硬币的 `on_hit` 上 → 该硬币再投一次（`ctx.repeat_extra`）。
  * 技能级：`{"kind": "repeat_coin", "times": N, "all_coins": true}` →
    技能所有硬币各多投 N 次（计划书要求的「多硬币 + 重投 E.G.O」）。
* 重复投掷产生的硬币**会**重新触发 [命中时] 效果与状态钩子（计划书 §18.1）。
* 但重复投掷**不会**再触发新的重复投掷（`is_repeat_throw` 保护），
  另加 `max_repeat_per_coin` 安全阀，避免无限递归（这个坑已经踩过一次）。
* 「追加硬币」`add_coin` 在技能末尾追加指定硬币。

## 7. 缩放与平衡（重要）

* 中文 Wiki 记录本体 HP = **25616**（`config.boss_hp` 保留该值）。
* 7 人各 1 槽、每次行动 3~4 枚硬币的尺度下，直接使用 25616 会让
  「Greedy 需要 40+ 回合」，对搜索/训练不友好。
  因此默认 `boss_hp_scale: 0.5`（≈12808），混乱/状态栈阈值按 HP 百分比同步缩放。
  **`boss_hp_scale: 1.0` 即完全按 wiki 数值。** 该字段会进 `config_hash`。
* 当前平衡（`python3 scripts/benchmark.py --seeds 5`，`max_turns=20`）：
  Greedy 即时伤害基线 0/5 胜（放宽到 30 回合时需 20~23 回合）；
  手写「沉沦 → 重投 E.G.O」轴 4/5 胜、中位 **7 回合**；
  关闭重复硬币 0/5、禁用蝶箱庄严哀悼 0/5、禁用目灯虫庄严哀悼中位 9.5 回合。
* 已知待调：**消融 F（关闭沉沦触发）的差距还不够大**——目前沉沦的收益主要体现在
  「把本体 SP 打到 -45 → 它拼点全出反面 → 攻击被拼点胜利抵消」，
  需要把 Boss 的威胁调高才能让 F 明显掉档；同理消融 A3（禁用和声）被手写轴的
  兜底技能掩盖。见 `docs/verification_checklist.md` §G。

## 8. 数据格式速查

技能（`data/identities.json` / `data/egos.json` / `data/boss_rr6_butterfly.json`）：

```jsonc
{
  "sid": "yi_s3", "name": "安魂", "sin": "gloom", "damage_type": "slash",
  "base_power": 6, "offense_level_mod": 0,
  "coin_count": 4,                       // 或直接写 "coins": [...]
  "coin": {
    "kind": "positive",                  // positive / negative
    "power": 4, "damage": 10,
    "effects": [ {"when": "on_hit", "kind": "add_status", "key": "sinking",
                  "potency": 2, "count": 2, "target": "other"} ]
  },
  "effects": [                            // 技能级时点
    {"when": "on_use", "kind": "consume_resource", "key": "living_butterfly",
     "amount": 5, "clamp": false},
    {"when": "on_use", "kind": "note_scale", "from": "consumed",
     "key": "living_butterfly", "damage": 1}
  ]
}
```

效果字段：`kind`（处理器名）+ `when`（时点）+ `if`（条件）+ 若干参数。
可用 `kind`：

```
add_status  set_status  remove_status  add_stack  transfer_damage
lose_sp  heal_sp  heal_hp  deal_damage
add_resource  set_resource  consume_resource  note_scale
modify_power  modify_damage  modify_damage_mult
repeat_coin  add_coin  branch  sum_status
set_state  log_event  change_form  force_stagger  ego_resist_override
```

条件字段（`core/conditions.py`）：

```
status{key,who,potency_gte,count_gte,potency_lte,count_lte}
resource{key,who,gte,lte,eq}      hp_pct{who,lte,gte}      sp{who,lte,gte}
coin_heads  coin_index_gte/lte    is_phantom  target_kind  time_type
form_is  turn{gte,lte}  staggered  chance  skill_tag  config{...}
all[]  any[]  not{}  branch_if{}
```

`who` 取值：`self`（技能使用者 / 状态持有者）与 `other`（目标 / 对手）。
目标 token：`self` `other` `all_allies` `all_enemies` `target_allies` `boss`
`phantom:past|present|future` `random_ally` `random_enemy` `lowest_hp_ally`。

## 9. 与 Rust 方案的对应关系

计划书 §5.1 建议用 Rust 写底层（可 clone/rollback/批量并行）。本机没有 Cargo，
因此用相同架构的 Python 实现：

| 计划书（Rust） | 本实现（Python） |
|---|---|
| `sim-core` | `rr6sim.core` |
| `rr6-data` | `rr6sim.content` + `data/*.json` |
| `pybridge`（PyO3） | `rr6sim.env`（直接 import） |
| 批量环境 | `simulate.step_many`（接口已固定，未并行化） |

移植时只需要保证 `Battle` 的时点调用顺序与 `state.hash()` 的规范序列化一致，
golden replay（`tests/golden/`）可以直接作为跨语言一致性测试。
