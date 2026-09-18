# rr6-butterfly-agent

《边狱巴士》**RR6 Line 6 / Section 5 / Station 8「Advent」** 的罗生蝶
（`Refracted Butterfly of Entangled Lives::Imago` + 三只幻影蝶）战斗模拟器。

目标（计划书）：固定 7 个人格 + 少量 E.G.O，在「尽量少回合击杀罗生蝶」这一目标下，
观察搜索/训练算法能否自行发现「沉沦 setup → 多 hit / Coin Reuse E.G.O 爆发」这类人类竞速策略。

> ## ⚠️ 当前状态：**prototype，机制已按 wiki 校准但数据未录全**
>
> * 本轮完成了一次完整的 mechanics audit（`docs/audit_report.md`），
>   并把**核心机制**从「上一版按记忆臆造」改成**按 wiki.gg 原文实现**：
>   真实伤害公式、Coin Reuse、Sinking/Butterfly、E.G.O 的 SP/侵蚀/Overclock、技能牌堆、
>   clone/state hash、合法目标。
> * **7 个人格的技能数值目前仍是占位数据（`confidence: synthetic`）**，
>   尚未逐页录入 —— 见 `docs/verification_checklist.md` §D。
> * 因此 **当前 benchmark 不能支持任何「策略最优性」结论**。
>   上一版 README 里「收益结构指向沉沦 → 重投 E.G.O」的说法**已被删除**：
>   那是建立在错误机制（自造的「沉沦越高 → 全硬币重投」）之上的。
>
> `READY_FOR_SEARCH = NO`（blocker 见 `docs/audit_report.md` 末尾与本文末）。

## 快速开始

```bash
# 全部测试（标准库 unittest，无需 pytest）
./run_tests.sh          # 若执行位丢失：bash run_tests.sh

# known-strategy regression test（只检查机制是否发生，不断言最优性）
python3 scripts/manual_line.py

# 冒烟 / 环境 API / replay
python3 scripts/smoke.py 0 --replay
python3 scripts/run_env.py --config configs/rr6_butterfly_base.yaml --laws --out runs/demo.json

# 消融矩阵（Greedy vs known line vs 各项开关）
python3 scripts/benchmark.py --seeds 3

# 取证工具（重新核对数据时用）
python3 tools/wiki_fetch.py page "Solemn Lament Gregor" --raw
python3 tools/wiki_fetch.py category "E.G.O with Coin Reuse"
```

## 本轮修复的核心机制（都有测试）

| 机制 | 修复前（错误） | 修复后（wiki.gg 原文） |
|---|---|---|
| **Coin Reuse** | 李箱庄严哀悼「目标沉沦越高 → 全技能硬币重投」（臆造）；和声消耗自造 `harmony` 资源 | 只有 **Gregor 庄严哀悼（第 3 枚，SP ≥ 0，最多 5 次）** 与 **和声（第 3 枚，Heads Hit + HP ≥ 10%，最多 4 次）** 有 reuse；**李箱庄严哀悼没有 reuse**，它是 5 枚 Unbreakable + 蝶结算 |
| **伤害公式** | `coin.damage × (1 + 0.03 × 等级差) × 抗性` | `Coin Roll × (1 + Static) × (1 + Dynamic)`；抗性分段函数；`M = (Off−Def)/(|Off−Def|+25)`；拼点每 3 级 +1 威力；混乱替换物理抗性 |
| **Sinking** | 只掉 SP | 掉 SP；**无 SP 单位（Abnormality）改为等强度 Gloom 伤害** |
| **Butterfly** | 命中时 SP + HP 伤害（臆造） | 攻击者回 (Living/4) SP；自身 SP<0 时按 `(Sinking Potency/5) × Departed` 造成 Gloom 伤害；回合结束 Living↔Departed 转换 |
| **E.G.O SP** | `SP < cost` 就不能用 | 可以用；**扣到 ≤ −45 必定侵蚀**；SP<0 时按概率侵蚀；Overclock = 1.5× 代价；同回合不能重复使用同一 E.G.O |
| **技能牌堆** | `[S1,S2,S3]` 循环 | **S1×3 / S2×2 / S3×1**，抽完才洗牌 |
| **clone / hash** | hash 不含 deck_queue / rng_state；flags 浅拷贝 | `transition_hash`（含 RNG、牌堆、flags 深拷贝…）+ `observation_hash`；clone 深复制（有隔离测试） |
| **合法目标** | 跳过 `slot.cancelled` → 混乱的 Boss / 不行动的幻影不可选 | 「会不会行动」与「能不能被打」分离；混乱目标仍可单方面攻击 |
| **Boss** | 自造的 bt_s1~bt_s4 + TimeGap + 幻影回补 | 真实 Imago：HP 25616（=9090+275.44×60）、4 段混乱阈值、12 技能、三套时间栈、**幻影被击中时本体失去对应栈**、三回合技能循环 |
| **Unbreakable Coin** | 无 | 拼点失败 → Cracked（威力固定 +1/−1），失败后仍结算 |

未实现的真实机制**不会静默失真**：数据里写 `not_implemented`，每次触发都计入
`state.counters["not_implemented"]` 并写进 replay。

## 仓库结构

```text
data/            # 世界数据（每条带 source / confidence：verified|high|medium|low|synthetic）
  statuses.json  identities.json  egos.json  boss_rr6_butterfly.json
configs/         # 实验配置（真实数值 / deterministic / stochastic / 消融矩阵）
src/rr6sim/
  core/          # 纯规则引擎：engine(时点/拼点/逐硬币/Coin Reuse) damage(真实公式)
                 # effects conditions status unit skill state context rng config
  content/       # loader（data -> 内容）+ mechanics（蝶/沉沦等专用 handler）
  env/           # 自回归动作空间 + 观察 + Gym 风格 env
  simulate.py    # clone_state / state_hash / step_from_state / step_many / simulate_to_turn_end
  verify.py      # replay 重跑与逐事件审计
  replay.py      # replay 导出 / 文本化
  search/greedy.py
tests/           # unit(99) + golden(6) + replay(7)
tools/wiki_fetch.py
docs/            # audit_report / mechanics_notes / verification_checklist / sources
_sources/        # wiki 抓取缓存（gitignore）
```

## 真实 vs synthetic 配置（benchmark 必须说明）

* `boss_hp_scale`（默认 **0.5**）：wiki 真实 HP = **25616**（= 1.0）。
  默认缩放只是为了把回合尺度压到搜索/训练可用范围 —— **这是 curriculum，不是游戏数值**。
* `data/identities.json`：人格技能数值 = **synthetic 占位**。
* `encounter_buffs`：第五区段事件增益（含第 4 回合的 Choice Event）注入口。
* 消融开关：`coin_reuse_enabled`、`sinking_vs_no_sp_deals_gloom_damage`、
  `corrosion_mode`、`disabled_egos`、`disabled_rr6_passives`（关掉后机制真的不生效，有测试）。

## 已知 blocker（放行 Beam/MCTS 前必须解决）

1. **7 个人格的数据录入**（`data/identities.json` 目前是 synthetic）
2. **Poise / 暴击**、**Imago 技能的「按时间栈提升伤害」**、**Burn/Bleed 完整口径**
   —— 这三项会直接影响伤害量级
3. E.G.O 侵蚀形态的完整效果文本（当前只有基础数据）
4. 幻影蝶 Section 5 版本的数据（wiki 页面用的是 Section 2~4 版本）

详见 `docs/verification_checklist.md`（§B/§C/§D）与 `docs/audit_report.md` 末尾。

## 工程原则

1. 真实机制正确性 > 状态转移 > clone/hash/replay > 测试 > 搜索 > RL > 性能
2. 奖励里绝不出现沉沦/蝶/重投/E.G.O 名称；默认连 HP shaping 都是 0
3. 任何影响结算的开关都进 `SimConfig` 并计入 `config_hash`（replay 可追溯）
4. 查不到的机制写 `not_implemented` + `confidence`，不推测
5. 改数值只改 `data/*.json`，不改代码
