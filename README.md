# rr6-agent —— RR6 罗生蝶「沉沦 + 重骰 E.G.O」策略涌现实验

本仓库是计划书 `../rr6_butterfly_agent_plan.md` 的**模拟器部分（M0~M5，M6 起点）**实现：
一个**可验证、可复现、可回放**的《边狱巴士》RR6 第五区段罗生蝶战斗模拟器。

第一阶段只回答一个问题：

> 固定一组人格和 E.G.O，面对 RR6 第五区段的罗生蝶，如果唯一核心目标是尽量少回合击杀，
> 算法能否自己学会「先建立沉沦 / 蝶等状态，再用多硬币、重投硬币 E.G.O 进行爆发」的结构？

## 两个环境前提（影响交付形态，请先读）

1. **本机没有 Rust / Cargo，也没有 pip。**
   计划书 §5.1 推荐的 Rust 底层，这里用**纯 Python 标准库**实现了同一套架构
   （事件时点引擎 + 数据驱动 + 可 clone/state_hash/replay），
   接口按计划书 §11 的约定保留（`legal_actions` / `clone_state` / `state_hash` /
   `step_from_state` / `step_many` / `simulate_to_turn_end`）。
   对应关系见 `docs/mechanics_notes.md` §9，后续可以原样移植回 Rust，
   `tests/golden/` 可直接当跨语言一致性测试。
2. **Wiki 在本机被 403 拦截。**
   `limbuscompany.huijiwiki.com` 完全取不到（含 `api.php`），因此
   **`data/*.json` 里的数值是按游戏机制结构重建的近似值**，机制保真、数值待校验。
   每个文件和条目都带 `source` / `confidence`；校验清单见
   `docs/verification_checklist.md`。**不要把这些数字当成百科事实直接引用。**

## 快速开始

```bash
# 1) 全部测试（标准库 unittest，无需 pytest）
./run_tests.sh          # 若执行位丢失：bash run_tests.sh

# 2) 冒烟：跑一局 Greedy，打印关键统计
python3 scripts/smoke.py 0
python3 scripts/smoke.py 0 --replay          # 带逐事件 replay

# 3) 手工「沉沦 -> 重投 E.G.O」轴 + 消融对比
python3 scripts/manual_line.py

# 4) 基准矩阵（Greedy vs 手写轴 vs 各消融项）
python3 scripts/benchmark.py --seeds 5

# 5) 环境 API 演示 / 导出 replay
python3 scripts/run_env.py --config configs/rr6_butterfly_base.yaml --seed 1 --out runs/demo.json
```

### 当前基准（`scripts/benchmark.py --seeds 5`，默认 `boss_hp_scale=0.5`，`max_turns=20`）

| 配置 | 胜率 | 击杀回合（中位） | 未击杀时剩余 HP |
|---|---|---|---|
| Greedy 即时伤害基线 | 0/5 | — | ~2207 |
| 手写「沉沦 → 重投 E.G.O」轴 | 4/5 | 7 | 246 |
| A1 禁用蝶箱庄严哀悼 | 0/5 | — | ~2668 |
| A2 禁用目灯虫庄严哀悼 | 4/5 | 9.5 | 1981 |
| A3 禁用辛克莱和声 | 4/5 | 7 | 246 |
| E 关闭重复硬币 | 0/5 | — | ~3951 |
| F 关闭沉沦触发 | 5/5 | 7 | — |
| G 关闭蝶特殊沉沦 | 3/5 | 8 | 1933 |

Greedy 不是「打不死」，而是**在 20 回合内打不完**：把上限放宽到 30 回合后，
它需要 20~23 回合（5 次里 3 次成功，2 次被反杀）。

结论：**在没有任何「沉沦/重投」专属奖励的前提下**，单靠「少回合击杀」这个目标，
模拟器里的收益结构确实指向「先堆沉沦 → 再放重投 E.G.O」，且拆掉任一环节都会变差
（A1/A2/E 掉档最明显）。已知不足：A3 被手写轴的兜底技能掩盖、
F（关闭沉沦触发）目前几乎无影响——两项都记在 `docs/verification_checklist.md` §G。

## 仓库结构

```text
rr6-agent/
├─ data/                       # 世界数据（带来源 / 置信度）
│  ├─ statuses.json            # 状态定义 + 触发钩子
│  ├─ identities.json          # 7 个人格：技能 / 被动 / 专属资源
│  ├─ egos.json                # 6 个重点 E.G.O（觉醒 + 侵蚀 + 抗性覆盖）
│  └─ boss_rr6_butterfly.json  # 罗生蝶本体 + 三幻影 + 形态/阈值
├─ configs/                    # 实验配置（这次实验用什么规则）
│  ├─ rr6_butterfly_base.yaml
│  ├─ deterministic.yaml       # Stage A
│  ├─ stochastic.yaml          # Stage E
│  └─ ablation_matrix.yaml     # 消融矩阵
├─ src/rr6sim/
│  ├─ core/                    # ★ 纯规则引擎（无 IO、无第三方依赖）
│  │  ├─ engine.py             # 回合流程 / 拼点 / 逐硬币结算 / 罗生蝶机制
│  │  ├─ effects.py            # Effect 处理器（数据驱动的效果集合）
│  │  ├─ conditions.py         # 条件表达式
│  │  ├─ status.py unit.py skill.py state.py context.py
│  │  ├─ damage.py             # 伤害公式 + DamageBreakdown
│  │  ├─ rng.py                # SplitMix64（可回滚 / 可 hash）
│  │  └─ config.py             # 所有开关与常数（含消融开关）
│  ├─ content/loader.py        # data/*.json -> 可执行内容
│  ├─ env/                     # 自回归动作空间 + 观察 + Gym 风格环境
│  ├─ simulate.py              # clone/step_from_state/step_many/simulate_to_turn_end
│  ├─ verify.py                # replay 重跑与逐事件审计
│  ├─ replay.py                # replay 导出 / 文本化
│  └─ search/greedy.py         # Greedy 基线（搜索基线的起点）
├─ tests/
│  ├─ unit/                    # 58 个最小机制测试（计划书 §18.1）
│  ├─ golden/                  # golden replay（事件摘要 + 终局 hash）
│  └─ replay/                  # replay 往返 / 篡改检测
├─ scripts/                    # smoke / manual_line / benchmark / run_env
└─ docs/
   ├─ sources.md               # 数据来源与置信度（M0）
   ├─ mechanics_notes.md       # 实现口径 / 公式 / 假设 / 数据格式
   └─ verification_checklist.md# 待游戏内校验清单
```

## 已经实现（对应计划书里程碑）

* **M1 最小伤害引擎**：技能基威 / 硬币威力 / 正负硬币 / 攻防等级 / 物理罪孽抗性 / 逐硬币结算。
* **M2 沉沦 + 重投木桩**：沉沦（强度累积 + 命中触发）、E.G.O SP 消耗、觉醒/侵蚀、
  重复投掷（硬币级 + 技能级「所有硬币」）、追加硬币。
* **M3 7 人固定队伍**：7 个人格各自的技能组、专属资源（生蝶 / 目灯 / 光札 / 和声 / 弹药）、
  被动、6 个 E.G.O。
* **M4 罗生蝶静态 Boss**：本体 + 三幻影 + 过去/现在/未来状态栈 + 形态切换 + 混乱阈值 +
  伤害转移 + 未受击回补 + HP 阈值补栈。
* **M5 完整确定性战斗**：回合流程、速度与行动顺序、拼点、单方面攻击、改目标、
  混乱/死亡、E.G.O 抗性覆盖、可回放 replay。
* **M6 起点**：Greedy 基线 + `benchmark.py` 消融矩阵。

尚未实现（计划书后续里程碑）：Beam Search / MCTS（M6）、policy/value 与 Expert Iteration（M7）、
跨 seed 统计（M8）、完整消融与结论（M9）。

## 最小 API

```python
from rr6sim import RR6ButterflyEnv, SimConfig, Content
from rr6sim.search.greedy import greedy_plan

env = RR6ButterflyEnv(SimConfig(max_turns=20), seed=1234)
obs = env.reset(seed=1234)
legal = env.legal_actions()          # 当前决策点的合法动作（含人类可读 label）
mask = env.legal_action_mask()
obs, reward, terminated, truncated, info = env.step(0)
plan = greedy_plan(env.battle)       # 或者直接给一整回合的计划
obs, reward, term, trunc, info = env.step_plan(plan)
replay = env.export_replay()
```

状态机层面（计划书 §11，MCTS/Beam 更需要这几个）：

```python
from rr6sim.simulate import new_battle, clone_state, state_hash, simulate_to_turn_end, step_many
from rr6sim.verify import verify_replay

ok, report = verify_replay(content, replay)   # 逐事件审计一条 replay
```

## 工程原则

1. **规则正确性 > replay/测试 > 搜索基线 > 训练模型 > 性能优化**（计划书 §26）。
2. 奖励里**绝不**出现沉沦、蝶、重投、庄严哀悼、和声等字样；
   默认配置连 HP shaping 都是 0（`reward_hp_shaping: 0.0`）。
3. 任何会改变结算的开关都进 `SimConfig` 并计入 `config_hash`，replay 里可追溯。
4. 每条不确定的数值都能在 `docs/` 里找到出处与置信度标注；
   改数值只需要改 `data/*.json`，不用碰代码。
