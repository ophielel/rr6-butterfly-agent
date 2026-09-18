# 机制笔记（实现口径 / 公式 / 假设 / 出处）

> 本文档回答：**模拟器里的每条规则来自哪里、置信度多高、和游戏不一致时该改哪里。**
>
> 证据来源：`limbuscompany.wiki.gg`（本机直连被 Cloudflare 拦截，用 `tools/wiki_fetch.py`
> 经 `r.jina.ai` 代理抓取 MediaWiki API）。原始抓取结果缓存在 `_sources/`（gitignore）。
>
> 配套文档：`docs/audit_report.md`（本轮审计发现的问题与修复状态）、
> `docs/verification_checklist.md`（逐条待校验清单）、`docs/sources.md`（来源汇总）。

## 0. 原则

* **真实机制正确性 > 状态转移正确 > clone/hash/replay > 测试 > 搜索 > RL > 性能。**
* 不允许为了 benchmark 好看而调数值；不允许为了让「沉沦 + 重投」成为最优而改规则。
* 查不到的机制：不推测，写 `not_implemented` / `confidence: low|synthetic` 并记录 TODO。
* 每个 `not_implemented` 触发都会计入 `state.counters["not_implemented"]`，并在 replay 里留日志——
  **未实现的机制不会静默失真**。

## 1. 数据置信度标注

`data/*.json` 每个条目都有 `source` 与 `confidence`：

| 值 | 含义 |
|---|---|
| `verified` | 已对照 wiki.gg 页面原文逐字录入 |
| `high` | 结构/数值来自 wiki，个别数值待复核 |
| `medium` | 机制方向正确，具体数值待复核 |
| `low` | 只有大致方向，数值明显需要校验 |
| `synthetic` | **实验为了课程/平衡人造的**，游戏里不存在（必须单独说明） |

当前状态：

* `data/egos.json` = **verified**（6 个 E.G.O 全部按 wiki 原文重录）
* `data/boss_rr6_butterfly.json` = **high**（Imago 本体 12 技能 + 3 幻影 + passive 结构）
* `data/statuses.json` = 混合（Sinking / Butterfly / Fragile 等 verified；Burn/Bleed 等 medium）
* `data/identities.json` = **synthetic**（7 个人格的技能数值是占位数据，尚未逐页录入）

## 2. 事件时点表

`rr6sim.core.enums.Timing`：

```
battle_start
turn_start                     # 状态钩子、被动、Imago 激活时间状态
speed_roll / skill_choices_ready
（自回归构造本回合计划）
combat_start
  per 行动槽（速度降序）:
    on_use                     # [使用时]
    before_clash
    on_clash_win / on_clash_lose
    before_attack              # [攻击前]
      per 硬币:
        coin_start
        before_coin
        on_coin_heads / on_coin_tails        # 硬币正/反面
        heads_hit / tails_hit                # [Heads Hit] / [Tails Hit]
        on_hit                               # [命中时]
        hit_after_clash_win / hit_after_clash_lose
        on_hit_without_cracking              # Unbreakable Coin 专用
        after_coin / current_coin_attack_end
    after_attack / attack_end
    on_stagger / on_death
turn_end
combat_end                     # 跨回合的「Combat End」（如和声的 -8 SP）
```

单枚硬币的结算顺序（`Battle.resolve_coin`）：

1. `coin_start` → `before_coin`
2. `on_coin_heads|tails` → `heads_hit|tails_hit`
3. `on_hit`（硬币与技能的 [命中时] 效果，**先施加状态**）
4. `hit_after_clash_win|lose`、`on_hit_without_cracking`（cracked 硬币）
5. 伤害结算（`damage.deal`）→ 护盾吸收 → 幻影处理 → 混乱 → 死亡 → HP 阈值
6. 目标身上「命中时」状态钩子（`sinking_trigger` / `butterfly_trigger`）
7. 攻击者身上「命中时」状态钩子 + 攻击者被动
8. `after_coin`

> 「先施加状态再触发」是刻意选择（沉沦队在同一枚硬币上「施加→触发」的手感）。
> 若游戏实际相反，交换第 3 与第 6 步即可（在 `resolve_coin` 里调整）。

## 3. 伤害公式（**已改为真实公式**）

```
Final Damage = Coin Roll × (1 + Static) × (1 + Dynamic)
```

* **Coin Roll = 该硬币的 Final Power**（`base_power + 有利面时 coin.power + 修正`）。
  → 旧实现里独立的 `coin.damage` 字段是**模拟器近似量**，现在只作为 *attack adder* 使用
  （`Coin.damage`，默认 0；`data/*.json` 里若出现请视为 synthetic）。
* `Static = Sin Res Mod + Damage Res Mod + Off/Def Level Advantage + Crit
  + Clash Count × 0.03 + Observation Level`
* 抗性分段：

```
x < 0      → -0.5      # Immune 实际吃一半伤害
0 ≤ x < 1  → (x-1)/2   # Ineff. x0.5 实际 -25%
x ≥ 1      → x-1       # Weak x1.5 → +50%，Fatal x2 → +100%
```

* 攻防等级：`M = (Off - Def) / (|Off - Def| + 25)`（`offense_defense_modifier`）
* 拼点：**高等级方每 3 级差 +1 拼点威力（向下取整）**（`clash_level_bonus_per_3 = 1.0`）
* 混乱：该回合**物理抗性被替换**为 `Stagger Level × 0.5 + 0.5`
  （Stagger/+/++ = +1 / +1.5 / +2），与已有弱点取较高者，**不叠加**
* 取整：向下取整、最低 1、且不低于 `0.05 × Coin Roll`
* 固定伤害（状态类如沉沦）：`flat=True` → 忽略物理抗性与等级，只乘罪孽抗性

## 4. Coin Reuse（重骰）—— 实验核心

**只有两个参与实验的 E.G.O 有 Coin Reuse**（`Category:E.G.O with Coin Reuse`）：

| E.G.O | 真实文本 | 实现 |
|---|---|---|
| 庄严哀悼（格里高尔） | 第 3 枚 `[On Hit] At 0+ SP, Reuse this Coin (5 times max per Skill)`，每次命中 -2~6 SP | `reuse_coin(coin="current", max_reuse=5, if=SP>=0)`，写在**第 3 枚硬币**的 effects 里 |
| 和声（辛克莱） | 第 3 枚 `[Heads Hit] At 10%+ HP, take 4~8 HP damage → Then, Reuse this Coin (4 times per Skill)` | `self_harm` + `reuse_coin(max_reuse=4, if=HP>=10%)`，触发条件是 `heads_hit` |

实现细节（`effects._h_reuse_coin` + `engine.strike`）：

* 指定硬币（`coin: "current" | 索引 | "last" | "first"`），**不是把整个技能重打一遍**；
* `max_reuse` 是**每技能**上限，用 `frame["reuse_counts"]` 计数；
* **每次 reuse 前重新判定 `if` 条件**（所以 Gregor 在 SP 变负后会停止 reuse）；
* reuse 的硬币会重新走完整结算，**重新触发 [On Hit]**；
* reuse 产生的硬币可以再次 reuse（真实机制靠 `max_reuse` 封顶），
  用 `allow_recursive` 只是给 synthetic 效果用的开关；
* 带 `"reuse_only": true` 的效果对应游戏文本的 `Reuse - ■■■` 前缀（只在被 reuse 的硬币上触发）。

`synthetic` 的 `repeat_coin`（全硬币重复投掷）**必须显式写 `"synthetic": true`**，
否则 handler 直接抛错——游戏里不存在这种写法，禁止再被当作真实规则使用。

## 5. E.G.O 的 SP / 侵蚀 / Overclock（**已改为真实规则**）

* E.G.O **不因 SP 不足而被禁用**（SP 可以为负，扣到 −45 也允许）。
* `slot.corrosion = True` 表示玩家主动 **Overclock**：花 `ceil(1.5 × 觉醒消耗)` 的 SP，
  使用**侵蚀技能**但去掉 Indiscriminate（稳定目标）。
* 否则（`corrosion_mode`）：
  * `rng`（真实）：若「当前 SP − 觉醒消耗 ≤ −45」→ **必定侵蚀**（按侵蚀技能的 SP 消耗扣）；
    若 SP < 0 → 按概率侵蚀（`corrosion_chance_at_min_sp`，曲线待校验，标 low）；
  * `auto_only`：只保留必定侵蚀（deterministic curriculum）；
  * `never`：永远觉醒（对照实验用）。
* 同一回合同一 E.G.O 不能使用两次（`allow_same_ego_twice_per_turn=False`）。
* 使用后本回合罪孽抗性被该 E.G.O 的抗性表覆盖（`resist_override`，7 罪孽逐项，来自 wiki 的 res 表）。

## 6. 技能牌堆（Skill Deck）

wiki.gg/Battles：**「3 copies of Skill 1, and 1 copy of Skill 3」**，抽完才重新洗牌。

* 数据层显式写份数：`"deck": {"yi_s1": 3, "yi_s2": 2, "yi_s3": 1}`；
* 每个行动槽每回合抽 2 个候选；队列空时才 refill；
* `skill_draw_mode=fixed`：按声明顺序，完全可复现；`rng`：洗牌，同 seed 可复现。

## 7. 状态（按 wiki 原文实现）

| key | 中文 | 实现要点 | 置信度 |
|---|---|---|---|
| `sinking` | 沉沦 | 命中时失去等同强度的 SP；**无 SP 单位改为等强度 Gloom 伤害**（忽略物理抗性）；层数 −1 | verified |
| `butterfly` | 蝶 | Potency = The Living / Count = The Departed；命中时**攻击者回复 (Living/4) SP**；自身 SP<0 时每个 Departed 造成 `(Sinking Potency/5)` Gloom 伤害（上限 30，无 SP 单位减半）；回合结束 Departed→0、获得等同 Living 的 Sinking、Living→Departed | verified |
| `fragile` | 脆弱 | 每层 +10% 动态修正 | high |
| `rupture` / `burn` / `bleed` | 破裂/燃烧/出血 | 固定伤害，层数 −1（触发口径 medium） | medium |
| `manor_echo` | 山庄的回响 | 回合结束 −1；50% 追加 Sinking Count、Panic 类型、无 SP 单位 −10% 正面率 → **未实现** | high（文档）/ 部分未实现 |
| `dazzle` | 眩惑 | 机制已记录，伤害加成接入 **未实现** | high（文档）/ 部分未实现 |
| `sheut_fracture` / `blue_sand` / `blessing` | 影之龟裂 / 青沙 / 加护 | 机制已记录，触发 **未实现** | high（文档）/ 部分未实现 |
| `in_the_past` / `in_the_present` / `in_the_future` | 过去/现在/未来 | Imago 三套状态栈 | verified |

`timegap`、`dead_butterfly`、`despair` 等**上一版臆造的状态已删除**。

## 8. 罗生蝶（RR6 Line 6 / Section 5 / Station 8「Advent」）

真实结构（`data/boss_rr6_butterfly.json`）：

* 本体 `Refracted Butterfly of Entangled Lives::Imago`：
  * `hp = 9090 + 275.44 × 60 = 25616`（与计划书记录一致），level 60，speed 1~3，defmod +0
  * 4 个混乱阈值：85% / 65% / 40% / 10%
  * 抗性：wrath/lust/pride 1.25，sloth/gluttony 0.75，gloom/envy 1.0，物理全 1.0
  * **`has_sanity = false`（Abnormality）** → 沉沦直接转 Gloom 伤害，这是沉沦队的真实收益
  * 12 个技能（spower / cpower / coin / atkmod / atkweight / 类型 / 罪孽 全部按 wiki 录入）
  * `Moment of Entangled Lives`：回合开始激活三套时间栈中最高者；**幻影被作为主要目标攻击时本体失去对应栈**
  * `三世因果`：开战三栈各 10；HP 首次低于 66%/33% 时三栈各 +10
  * 技能循环：按激活状态 + HP 阶段（normal / below_66 / below_33）的三回合循环
* 三只幻影蝶（`Illusory Butterfly::The Past / The Present / The Future`）：`hp=1`、**333 Shield**、
  `Take +100% damage from E.G.O Skills`、`Eclosion`（Unclashable / 0 伤害 / Attack End 结束遭遇）
* Section 5 的开局状态 = **通关 Section 1（The Pupa）时的 HP% 与 SP** → 本实验由 config 注入

未实现（已在数据里标 `not_implemented`，并计入 counters）：Poise/暴击、Unbreakable 的 Crack
细节、Burn/Bleed 完整口径、Scale Dust、Temporal Disjunction、攻击权重/子目标/部位破坏、
随机硬币目标。

## 9. 实验配置：真实 vs synthetic

| 字段 | 性质 | 说明 |
|---|---|---|
| `boss_hp_scale` | **synthetic curriculum** | wiki 真实 HP = 25616（= 1.0）。默认 0.5 是为了把回合尺度压到搜索/训练可用的范围 |
| `encounter_buffs` | synthetic | 第五区段事件增益（如第 4 回合的 Sunset Wayfarer Choice Event） |
| `disabled_rr6_passives` | 真实存在 | 前三段的禁用被动选择（配置项） |
| `curriculum_boss_sp_recovery` | **synthetic** | 真实 Imago 没有「每回合 +8 SP」；已从数据中移除 |
| `corrosion_chance_at_min_sp` | low | 侵蚀概率曲线的具体数值未校验（界面百分比是逐 E.G.O 的） |
| `coin_reuse_enabled` / `sinking_vs_no_sp_deals_gloom_damage` | 消融开关 | 关闭时对应机制真的不会生效（有测试） |

**任何 benchmark 结果都必须同时报告用的是哪种配置**（真实数值 or scaled curriculum）。

## 10. 与 Rust 方案的关系

计划书 §5.1 建议 Rust 底层；本机无 Cargo，因此用同架构的 Python 实现：
`core/`（规则）、`content/`（数据 + 专用 handler）、`env/`（自回归动作 + 观察）、
`simulate.py`（clone/hash/批量）。移植时以 `tests/golden/` 作为跨语言一致性测试。
