# 待校验清单 / 置信度台账

> 审计与修复过程见 `docs/audit_report.md`；实现口径见 `docs/mechanics_notes.md`。
>
> 勾选方式：`[x]` 已在 wiki.gg 页面原文确认；`[~]` 部分确认；`[ ]` 未确认（需游戏内或录像复核）。

## A. 已 verified（有 wiki.gg 原文支撑，实现与文本一致）

### A1. Sinking / Butterfly / SP
- [x] 精神力公式 `H = 50 + SP`（%），SP ∈ [−45, 45]
- [x] 沉沦：命中时失去等同强度的 SP、层数 −1；上限 99/99
- [x] **无 SP 单位（Abnormality）受到沉沦 → 等强度 Gloom 伤害**（忽略物理抗性，受罪孽抗性影响）
- [x] 蝶：Potency = The Living / Count = The Departed；上限 15
- [x] 蝶：命中时**攻击者**回复 (Living/4) SP（min 1）
- [x] 蝶：自身 SP<0 时，每个 Departed 造成 (Sinking Potency/5) Gloom 伤害（上限 30）
- [x] 蝶：回合结束 Departed→0 → 获得等同 Living 的 Sinking → Living→Departed
- [x] 「施加蝶时有概率变成 The Departed，否则 The Living」按**每层独立**判定

### A2. 伤害 / 拼点 / 混乱（`Damage Formula` + `Battles`）
- [x] `Final = Coin Roll × (1 + Static) × (1 + Dynamic)`，Coin Roll = 硬币 Final Power
- [x] 抗性分段函数（Immune 实际吃半伤；Ineff. 实际 −25%）
- [x] 攻防等级 `M = (Off − Def)/(|Off − Def| + 25)`
- [x] 拼点：高等级方每 3 级差 +1 拼点威力（向下取整）
- [x] 混乱：物理抗性被替换为 `Stagger Level × 0.5 + 0.5`，与已有弱点取较高者
- [x] 混乱持续「本回合剩余 + 下一回合」，混乱期间无法行动
- [x] 伤害向下取整、最低 1、不低于 `0.05 × Coin Roll`
- [x] Unbreakable Coin：拼点失败不破坏 → Cracked（威望固定 +1/−1），失败后仍会结算
- [x] `Clash Count × 0.03` 属于静态修正

### A3. E.G.O
- [x] `Category:E.G.O with Coin Reuse` 成员：Harmony Sinclair / Magic Bullet Outis /
      Solemn Lament Gregor / Tears of the Tarnished Blood Sinclair / Unbrilliant Glory Gregor /
      Wingbeat Ishmael
- [x] Gregor 庄严哀悼：第 3 枚硬币 `[On Hit] At 0+ SP, Reuse this Coin (5 times max per Skill)`，-2~6 SP/次
- [x] Harmony 和声：第 3 枚 `[Heads Hit] At 10%+ HP, take 4~8 HP → Reuse (4 times/Skill)`
- [x] **李箱庄严哀悼没有 Coin Reuse**：5 枚 Unbreakable 硬币 + 蝶结算
- [x] E.G.O 不因 SP 不足而不可用；「SP 消耗后 ≤ −45」必定侵蚀
- [x] Overclock = 1.5× 代价换「去掉 Indiscriminate 的侵蚀技能」
- [x] 同一回合同一 E.G.O 不能用两次
- [x] 6 个实验用 E.G.O 的 SP 消耗 / 罪孽抗性表 / 基础技能数据（spower、cpower、coin 数、atkmod）

### A4. 牌堆 / Imago
- [x] 技能牌堆：S1 × 3 / S2 × 2 / S3 × 1，**抽完才洗牌**
- [x] Imago HP = 9090 + 275.44 × 60 = 25616；level 60；speed 1~3；defmod +0
- [x] Imago 混乱阈值 85/65/40/10（%）
- [x] Imago 抗性表（wrath/lust/pride 1.25，sloth/gluttony 0.75，gloom/envy 1.0）
- [x] Imago 12 个技能的基础数据
- [x] Imago `Moment of Entangled Lives`：激活最高栈的时间状态；**幻影被作为主要目标攻击时本体失去对应栈**
- [x] Imago `三世因果`：开战三栈各 10；HP 首次 <66%/<33% 时三栈各 +10
- [x] Imago 三回合技能循环（按状态 + HP 阶段）
- [x] 三幻影蝶：hp=1 + 333 Shield、E.G.O 受伤 +100%、Eclosion（0 伤害 Unclashable）
- [x] Line 6 Section 5 = Station 8「Advent」；开局继承 Section 1 的 HP%/SP；Chain Battle + Backup
- [x] 第 4 回合开头的 Choice Event（Sunset Wayfarer's Sap A5 / Moth B5）

## B. 已实现但数值/口径待复核（low / medium）

- [ ] 侵蚀概率曲线：界面百分比是逐 E.G.O 的，当前用 `|SP|/45 × corrosion_chance_at_min_sp × 2` 近似
- [ ] 拼点胜利 +1 SP / 失败 ±0（wiki 只说「赢拼点涨 SP」，具体值未找到）
- [ ] 混乱时「伤害类型抗性替换」是否也影响罪孽抗性（当前只替换物理）
- [ ] `Chaotic Turmoil` 的 reuse 分档：「once for every 33% missing HP (max 2 times)」
      当前近似为「HP<100% 时最多 2 次」
- [ ] Burn / Bleed 的触发与层数消耗口径
- [ ] `Immolation` / `Kalpāgni` / `Skypiercer` / `Smite the Wicked` / `Bloodflower` 的
      「按 In the Past/Present/Future 栈提升伤害」当前标为 `not_implemented`
- [ ] 幻想蝶在 Section 5 的版本数据（页面用的 id 9564~9566 是 Section 2~4 版本；
      Section 5 波次为 9572~9574）

## C. 尚未实现（数据里已标 `not_implemented`，并计入 `counters["not_implemented"]`）

- [ ] **Poise / 暴击（Crit 静态修正）**
- [ ] 随机硬币目标（Gregor 庄严哀悼的 `Unfocused Volley`）
- [ ] 攻击权重 / 子目标 / 部位破坏（Severable Parts）
- [ ] Burn/Bleed 的「激活」类文本效果（如 `Activate Burn on target once`）
- [ ] Scale Dust（Incandescent / Acuate / Rusted）
- [ ] Temporal Disjunction / Wrath Fragility / HP Healing Down / Gloom Resist Down
- [ ] Rhythm（和声）、The Uninvited 的伤害加成、Sheut Fracture 满层爆发、Blue Sand 触发
- [ ] Panic / Low Morale（−30 低士气、−45 恐慌、E.G.O Corrosion 融合状态）
- [ ] Attack End 的 SP 回复/治疗（和声、Gregor 庄严哀悼的 `#hits × 3`）
- [ ] 和声的 `Combat End: lose 8 SP for 2 turns`
- [ ] E.G.O 侵蚀形态的完整效果文本（当前只有基础数据，效果标 low）
- [ ] Rest/Evade/Counter 防御技能；当前守备被简化为「不拼点 + 受伤 ×0.5」
- [ ] Focused Encounter 的改目标规则（真实规则：被指定的 Sinner 可无视速度反向锁定）
- [ ] Chain Battle / Backup Sinner / 撤退
- [ ] Section 5 第 4 回合的 Choice Event 效果（当前只作为 config 说明）

## D. synthetic（实验人造，**不是游戏规则**）

- [ ] `data/identities.json`：7 个人格的技能数值是**占位数据**，尚未按 wiki 人格页录入
- [ ] `boss_hp_scale`（默认 0.5）：wiki 真实 HP 是 25616（= 1.0）
- [ ] `encounter_buffs`：第五区段事件增益的注入口
- [ ] `corrosion_chance_at_min_sp`、`sinking_vs_no_sp_deals_gloom_damage`（消融）、
      `coin_reuse_enabled`（消融）
- [ ] `clash_model="reflex"`：synthetic 的拼点模型 B（真实模型尚未完全确认，默认用 advance）
- [ ] `Coin.damage`：attack adder，默认 0；真实伤害来自 Coin Roll

## E. 当前 benchmark 的地位（重要）

* 用**真实机制 + synthetic 人格数据**跑出来的结果**不能**支持任何「策略最优性」结论。
* `scripts/manual_line.py` 只作为 **known-strategy regression test**：
  它检查「沉沦会建立 / Coin Reuse 会发生 / 多次命中会重复触发状态 / replay 记录 / 消融生效」，
  并**明确接受**「Greedy 更强」这个结果。
* 在放行 Beam/MCTS 之前必须先完成：人格数据录入（§D 第 1 条）、
  以及 §C 中会影响伤害量级的项（Poise/暴击、按栈加成伤害、Burn/Bleed）。
