# Mechanics Audit Report — 2026-09-18

> 审计对象：`rr6-butterfly-agent`（上一版实现）。
> 结论先行：**READY_FOR_SEARCH = NO**。当前实现是「架构正确、机制大量错误或臆造」的原型，
> 其中跨点最严重的是 **E.G.O Coin Reuse 机制**、**伤害公式**、**状态语义**、**Boss 机制**。
>
> 证据来源：`limbuscompany.wiki.gg`（经 `r.jina.ai` 代理绕过 Cloudflare，见 `tools/wiki_fetch.py`）。
> 本机直连 wiki.gg / huijiwiki 都是 403。所有引用都在下文给出页面名与原文片段。

---

## 0. 取证方式

```bash
python3 tools/wiki_fetch.py page "Sanity" --raw        # 取 wikitext
python3 tools/wiki_fetch.py category "E.G.O with Coin Reuse"
python3 tools/wiki_fetch.py search "Coin Reuse"
```

* 抓取缓存：`_sources/`（gitignore）
* 本次审计抓取的页面：`Battles`、`Sanity`、`Damage Formula`、`Sinking`、`E.G.O/Gameplay`、
  `Harmony Sinclair`、`Solemn Lament Gregor`、`Solemn Lament Yi Sang`、
  `Line 6: Maru no Uchi no Sanzu no Kawa`、
  `Butterfly of Entangled Lives 羅生蝶/Enemy/Butterfly of Entangled Lives::Imago`、
  `Illusory Butterfly of Entangled Lives::The Past/Present/The Future`、`Category:E.G.O with Coin Reuse`

---

## 1. 【A 级】Coin Reuse / 重骰机制：当前实现是错的

### 1.1 谁真的有 Coin Reuse（verified）

`Category:E.G.O with Coin Reuse` 的完整成员（wiki.gg，2026-09-18 抓取）：

```
Harmony Sinclair
Magic Bullet Outis
Solemn Lament Gregor
Tears of the Tarnished Blood 汚血泣淚 Sinclair
Unbrilliant Glory Gregor
Wingbeat Ishmael
```

→ **`Solemn Lament Yi Sang`（蝶箱的庄严哀悼）不在这个分类里。**
当前 `data/egos.json` 给它写了「目标每 10 级沉沦强度 → 全技能硬币重复投掷」，**属于臆造**。

### 1.2 真实文案（原文摘录）

**Solemn Lament Gregor**（HP/Coin）：

```
|asanity=25 |csanity=30 |coin=3 |spower=8 |cpower=+2 |atkmod=+2 |atkweight=3
|se=When this Skill flips Coins, each Coin flips against a random enemy among its targets.
    - The first Coin always targets the main target ...
    When inflicting Butterfly using this Skill's effects: (Chance to flip Heads)% chance to inflict
    The Departed. If this unit did not inflict The Departed, inflict The Living instead.
    [Attack End] Heal (# of Coin 3 hits x 3) SP
|ce1=[On Hit] Inflict 1 random Butterfly
|ce2=[On Hit] Inflict 1 random Butterfly
|ce3=[On Hit] Inflict 1~2 random Butterfly
     [On Hit] Lose 2~6 SP
     [On Hit] At 0+ SP, Reuse this Coin (5 times max per Skill)
```

**Harmony Sinclair**：

```
|asanity=10 |csanity=30 |coin=3 |spower=6 |cpower=+2 |atkmod=+2 |atkweight=3
|ce3=[Heads Hit] At 10%+ HP, take 4 ~ 8 HP damage (once per Coin)
     - Then, Reuse this Coin (4 times per Skill)
     - This damage does not Stagger or reduce this unit's HP below 1
     [On Hit] Inflict 1 Burn / [On Hit] Inflict 1 Bleed
     [On Hit] A random ally gains 1~3 Rhythm next turn (once per Coin)
```

**Solemn Lament Yi Sang**（对照：没有 reuse）：

```
|asanity=20 |csanity=25 |coin=5 |spower=6 |cpower=+3 |atkmod=+4 |atkweight=3
|se=Unfocused Volley ... Clash Power +1 for every 4 (Sinking + both Butterfly) (max 4)
    [Before Attack] Gain a random assortment of (Gloom Reson. + 1) The Living & The Departed (max 7)
    [Attack End] Reload (Solemn Lament)
ce1..ce4 = Unbreakable Coin + [On Hit] Butterfly + [On Hit] +1 Sinking Count
ce5      = Unbreakable Coin + Spend all The Living & The Departed
           [On Hit] Inflict 3 Sinking / 3 Tremor / 2 Butterfly(The Living) / 2 Butterfly(The Departed)
           [On Hit] Trigger Tremor Burst; then reduce target's Tremor Count by 1
           [On Hit] Deal Gloom damage equal to the sum of both Butterfly on target
           [On Hit] Deal Gloom damage equal to (The Living & The Departed spent x 2)% of this Coin's final damage
```

### 1.3 「Reuse」的语义（verified）

`Battles` 页 Skill Tags 表：

* `Reuse - ■■■`：**「A prefix that may be applied to other already existing conditionals
  (e.g. `Reuse - On Hit`) that causes them to only activate on Reused Coins.」**
  → 存在专门给「被重复投掷的硬币」用的条件前缀，说明 **reuse 的硬币会重新走一遍硬币结算与 On Hit**。
* 重复次数上限写作 "N times max **per Skill**" → **计数是技能级的，不是每硬币级的**。
* 条件（SP ≥ 0 / HP% / 沉没值…）**每次 reuse 前重新判定**。

### 1.4 当前实现的错误

| 位置 | 现状 | 真实 |
|---|---|---|
| `data/egos.json` | 庄严哀悼（李箱）on_use：`sum_status(sinking) → repeat_coin(all_coins, max 2)` | **无 Coin Reuse**；应有 5 枚 Unbreakable 硬币、Butterfly 施加、第 5 枚消耗 Living&Departed 结算追加伤害 |
| `data/egos.json` | 和声：消耗自造 `harmony` 资源 → 全硬币重投 | 无该资源；应为 **第 3 枚硬币 [Heads Hit] 且自身 HP ≥ 10% → 自伤 4~8 → reuse（每技能最多 4 次）** |
| `data/egos.json` | 庄严哀悼（格里高尔）：沉沦门槛 → 全硬币重投 | 应为 **第 3 枚硬币 [On Hit] 且 SP ≥ 0 → reuse（每技能最多 5 次）**，每次命中额外 −2~6 SP |
| `core/effects.py` | `repeat_coin(times, all_coins)` 只有粗粒度 | 需要「指定第 N 枚硬币 / 每技能上限 / 每次重判条件 / 是否允许递归 reuse / 是否重新触发 On Hit」 |
| `core/engine.py` | reuse 由 `queue[i:i] = [ci]*n` 展开，无法逐次判定条件 | 需要在硬币结算循环里逐次判定 |

### 1.5 影响

这正好命中实验目标：**真实机制下「沉沦 setup → 多次命中」的收益来自
Gregor 庄严哀悼的 SP≥0 reuse（最多 6 次命中）与 Yi Sang 庄严哀悼的「第 5 枚硬币按 Butterfly 总和结算 Gloom 伤害」**，
而不是「沉沦越高 → 重投越多」这种臆造因果。当前实现会直接污染实验结论。

---

## 2. 【A 级】伤害公式：当前是臆造的线性近似

`Damage Formula` 页原文：

```
Coin Roll × (1 + Static Modifiers) × (1 + Dynamic Modifiers) = Final Damage
* Final damage is rounded down, cannot be less than 1.
* If Final Damage < 0.05 × Coin Roll → set to 0.05 × Coin Roll.
```

* **Coin Roll = 该硬币的 Final Power**（不是技能数据里独立的 `coin damage` 字段）。
  → 当前 `data/*.json` 的 `coin.damage`（12~30）是**模拟器近似量**，
  与 `spower`/`cpower` 两套数并存等于把伤害算了两遍。
* `Static Modifier = Sin Res Mod + Damage Res Mod + Off/Def Level Advantage + Crit + (Clash Count × 0.03) + Observation Level`
* Sin/Damage 抗性是**分段函数**（不是乘法）：

```
x < 0        → -0.5          # Immune 实际是吃一半伤害
0 ≤ x < 1    → (x-1)/2       # Ineff. x0.5 实际是 -25%
x ≥ 1        → x-1           # Weak x1.5 → +50%，Fatal x2 → +100%
```

* Off/Def Level Advantage（`Battles` 与 `Damage Formula` 两处一致）：

```
M = (Off - Def) / (|Off - Def| + 25)
```

  → 当前 `damage.py` 的 `1 + 0.03 × diff` 是错的（例如 diff=3 时真实 +10%，而 3% 线性给 +9%；
  diff=30 时真实 +0.55，线性给 +0.9）。

* 拼点：**`Battles` 页明确写「The Skill with higher Level gains 1 Power per 3 Level difference, rounded down」**
  → 当前默认 `clash_level_bonus_per_3 = 0.0` 是错的，应为 1。
* 混乱：不是「受到伤害 ×1.5」，而是**该回合把物理抗性替换为 Fatal**，
  静态修正为 `Stagger Level × 0.5 + 0.5`（Stagger/+/++ = +1 / +1.5 / +2），
  且不与此前已有的弱点叠加（取较高者）。

---

## 3. 【A 级】状态语义：多个核心状态实现错了

`Sinking` 页原文（表格）：

| 状态 | 真实规则 |
|---|---|
| **Sinking** | 命中时失去等同强度的 SP，层数 −1。**上限 99/99**。**无 SP 单位改为受到等强度的 Gloom 伤害**（忽略物理伤害类型抗性，但受罪孽抗性影响） |
| **Butterfly（蝶）** | 唯一 Sinking。Base 0 / **上限 15**。Potency = **The Living**，Count = **The Departed**。**命中时攻击者回复 (Living/4) SP（min 1）**；**命中时若自身 SP < 0，每个 Departed 造成 (Sinking Potency/5) Gloom 伤害（上限 30，无 SP 单位减半）**；**回合结束：Departed 归 0，然后获得等同 Living 的 Sinking，并把 Living 转换为 Departed**。外部效果不能提高施加量。两者都为 0 时消失 |
| **Echoes of the Manor（山庄的回响）** | 获得 Sinking Potency/Count 时 **50% 概率额外 +1 Count**；改变 Panic 类型；**无 SP 单位：−10% 正面概率**；回合结束 −1；**不叠加** |
| **Dazzle（眩惑）** | 每 1 点 (Sinking + Burn) 使**基础攻击技能**伤害 +0.5%（上限 10%）；无 SP 单位：Defense Level −2；回合结束 −1；不叠加 |
| **Sheut Fracture（影之龟裂）** | 上限 10；每层使受到 Sloth/Gloom 伤害 +1%；满层时获得 1 Gloom Fragility、受到等同 Sinking Potency 的 Gloom 伤害、Sinking Count −1，然后消失 |
| **Blue Sand（青沙）** | 拼点失败时 +1 Sinking Count（每回合 3 次）；无 SP：Speed ±1；回合结束 −1 |
| **Blessing（加护）** | 回合开始每 8 SP 获得 1 Protecting Sword（上限 5）；拼点结束时施加 2 Sinking（每回合 1 次）；被命中时对攻击者施加 2 Sinking（每回合 1 次）；每 20 SP 额外 +1 Sinking Potency |

对照当前实现：

| 当前 | 问题 |
|---|---|
| `butterfly` = 命中时 SP 伤害 + HP 伤害（都等于 potency） | 完全错误：真实是「攻击者回 SP」+「自身 SP<0 时按 Sinking Potency/5 × Departed 造成 Gloom 伤害」+「回合结束 Living→Departed 转换」 |
| `sinking` 命中掉 SP、层数 −1 | 基本正确，但缺「无 SP 单位 → Gloom 伤害」与 99 上限 |
| `manor_echo` 回合结束掉 2×层数 SP | 错误（真实是 panic 类型 + 50% 追加 Sinking Count + 无 SP 单位 −10% 正面率） |
| `dazzle` 通用「每层受伤 +5%」 | 错误（真实只对基础攻击技能、且按 Sinking+Burn 数量算、上限 10%） |
| `timegap`（时隙） | **游戏里没有这个状态**，是上一版臆造的 |
| `despair` / 负硬币「绝望罗」build | **错**。绝望罗 = `Lobotomy E.G.O::The Sword Sharpened with Tears Rodion`，真实机制是 **Blessing + Protecting Sword + 施加 Sinking**，不是「负理智/绝望」 |
| 目灯虫 = `Lobotomy E.G.O::Lamp Gregor` 的 Dazzle | 名字对了，机制写错 |
| 花札玛 = `Jeong's Office Rep Ishmael` + `Bygone Days Ishmael` E.G.O | 名称待复核；当前「光札 hikari」是臆造 |

---

## 4. 【A 级】E.G.O 的 SP / 侵蚀逻辑

`E.G.O/Gameplay` 原文：

```
All E.G.O cost Sanity (SP) to use. When E.G.O is used without falling to -45 SP, its intended
Awakening Skill will be used. ...
Using E.G.O without the required amount of Sanity has a chance of leading to the Awakening Skill
being replaced by its Corrosion variant. This happens automatically when the amount of Sanity
depleted by using the E.G.O brings the Sinners SP to -45 or lower. For example, using an E.G.O
with a cost of 20 Sanity while the Sinner is at -35 SP will always cause them to Corrode.
However, Sinners will have a chance of corroding whenever their Sanity is in the negatives,
not just at -45 SP. This chance is listed as a percentage beneath the Sanity requirement.
```

以及：

```
===Awakening & Corrosion===   （见上）
===Overclocking===  By spending 1.5x the amount of E.G.O Resources and Sanity, a
Stable Overclocked E.G.O Skill can be generated. This carries the same effects and power of the
Corrosion skill while removing its Indiscriminate nature ...
The same E.G.O cannot be used twice on the same turn, even if sufficient E.G.O Resources are
available (save for E.G.O Corrosion or external effects).
```

真实规则：

1. **E.G.O 不因「SP < cost」而被禁用**。SP 可以为负，扣到 −45 也允许。
2. **侵蚀是自动/概率判定的结果**，不是玩家随便勾选的开关：
   * 若「当前 SP − cost ≤ −45」→ **必定侵蚀**；
   * 若 SP < 0 → 按界面显示的百分比概率侵蚀；
   * SP ≥ 0 且扣完 > −45 → 觉醒。
3. **Overclock（超频）是玩家可主动选择的行为**：花 **1.5× 罪孽资源与 SP** 换取
   「去掉 Indiscriminate 的侵蚀技能」——所以「显式选择 corrosion」在真实游戏里**存在**，
   但代价是 1.5× SP，而不是免费按钮。
4. 同一回合同一 E.G.O 不能用两次（侵蚀或外部效果除外）。
5. 侵蚀技能通常随机/固定目标，且常常 Indiscriminate（可能打到队友）。

当前实现：
* `legal_actions()` 里 `if u.sp < ego.sp_cost: continue` → **错**（低 SP 就完全不能用了）。
* `corrosion=True/False` 作为并列的两个动作、且只收 `corrosion_sp_cost` → **错**（应是自动判定 + Overclock 1.5×）。

---

## 5. 【A 级】技能牌堆（Skill Deck）

`Battles` 页原文：

```
In combat, Sinners pull Skills out of a 'Skill Deck' which contains a certain number of each Skill
and will only refresh after all Skills have been used. The Skill's amount typically changes
inversely with its Skill Rank (i.e. 3 copies of Skill 1, and 1 copy of Skill 3).
```

→ 真实是 **3×S1 / 2×S2 / 1×S3（典型值）**，且**整副牌抽完才重新洗牌**。
当前实现是 `deck=[S1,S2,S3]` 循环、每槽抽 2 个、队列空了就立刻 refill → **错**。
需要：数据层显式写份数、抽空才 refill、fixed/rng 两种模式可复现。

---

## 6. 【A 级】clone / state hash（搜索前置条件）

当前 `BattleState.hash()`：

* 不包含 `deck_queue` / `deck_cursor` → 两个不同牌堆状态的局面会 hash 相同。
* 主动排除 `rng_state` → 对 Beam/MCTS/置换表是致命的。
* `flags` 浅拷贝（`dict(self.flags)`），但 `flags["targeted_phantoms"]` 是 list → 分支共享可变对象。
* `Unit.copy()` 对 `state` 只处理了一层 list。

结论：**必须拆成两个 hash**：

* `transition_hash`（默认 `state_hash()`）：包含 rng_state、deck_queue/cursor、flags(深)、
  Boss 隐藏状态、所有 counters、单位完整状态、resist_override、slots。
* `observation_hash`：只含玩家可见信息，用于训练诊断。

并且 clone 必须深复制（要有专门测试）。

---

## 7. 【A 级】合法目标选择

`legal_targets()` 里跳过 `es.cancelled` 的目标：

```python
for es in e.slots:
    if es.acted or es.cancelled:
        continue
```

这会把「敌人本回合不行动」错当成「不能被攻击」。真实规则里
「这个槽位会不会打出攻击」与「这个单位/部位能不能被打」是两件事：

* Boss 混乱 → 它的槽位取消，但 Boss **仍然是合法目标**（单方面攻击）。
* `phantom_acts=false` → 幻影不行动，但仍可被攻击。
* Focused Encounters 的 `Parts` 只有被破坏（Severable）后才不可选。

`Battles` 页原文（Parts）：

```
Severable Parts, when broken, are considered completely removed from the unit, making the Part
untargetable and unusable.
```

→ 合法目标应由 `alive / part 是否存在 / 是否被破坏 / 改目标与拼点规则` 决定。

---

## 8. 【B 级】罗生蝶 Boss：当前实现与真实战斗不符

### 8.1 真实数据（verified）

`Line 6: Maru no Uchi no Sanzu no Kawa`：8 站 / 5 区段。
* **Section 1 = Station 1 "Weighing of Robes" → Refracted Butterfly of Entangled Lives::The Pupa (id 9563)**
* **Section 5 = Station 8 "Advent" → Refracted Butterfly of Entangled Lives::Imago (id 9567)**
* Section 5 的开局状态 = **通关 Section 1 时的 HP% 与 SP**（与计划书「第五段开局状态注入」一致）；
  Section 1~4 每段结束会复活全体、满血、SP 归零。
* Line 6 = Chain Battle，全员上场 + 最后 5 人做 Backup（Backup 有额外初始 SP）。
* 装饰横幅条件：Section 5 通关且总回合 ≤ 111。

Imago 本体（`.../Enemy/Butterfly of Entangled Lives::Imago`）：

```
hp=9090  hpgrowth=275.44  level=60
→ 实际 HP = 9090 + 275.44 × 60 = 25616   ← 计划书的 25616 得到验证
speed=1~3   defmod=+0
stagger1=85 stagger2=65 stagger3=40 stagger4=10   （百分比）
slash/pierce/blunt = 1
wrath=1.25 lust=1.25 sloth=0.75 gluttony=0.75 gloom=1 pride=1.25 envy=1
```

技能 12 个（原文可见 `Fluttering Havoc` / `Pulverization` / `Chaotic Turmoil` / `Temper and Cast` /
`Immolation` / `Kalpāgni` / `Anitya` / `Skypiercer` / `Smite the Wicked` / `Corrosive Disintegration` /
`Rotting Annihilation` / `Bloodflower`），核心机制是：

* **Burn + Bleed + Poise** 三个 body 的循环；
* **`In the Past` / `In the Present` / `In the Future` 三套状态栈**（各技能写
  `Deal +(In the Past × 2)% damage (max 60%)`、`Clash Win: Gain 5 In the Past`、
  `Clash Lose: Halve In the Past`）；
* **Unbreakable Coin**：HP < 66% 时第二枚硬币转为 Unbreakable，HP < 33% 时全部转；
* **Reuse**：`Chaotic Turmoil` 的硬币「每 33% 缺失 HP reuse 一次（最多 2 次）」；
* `Smite the Wicked`：Attack End 若击杀目标则 reuse 整个技能（每回合 1 次）；
* 大量技能带 `Can Clash with this Skill regardless of Speed`。

Section 5 Wave 1 的敌人列表 = `9567 + 9572 + 9573 + 9574`
→ 对应「本体 + 三个 Illusory Butterfly」。`Illusory Butterfly of Entangled Lives::The Past/Present/The Future`
的页面（id 9564/9565/9566，Section 2~4 版本）显示：`hp=1`、`First Turn Start: Gain 333 Shield`、
被动 `Take +100% damage from E.G.O Skills`、技能 `Eclosion`（Unclashable、0 伤害、Attack End 结束遭遇），
以及 `Quadruple the effects of Incandescent/Acuate/Rusted Scale Dust`。

### 8.2 当前实现的错误

* `data/boss_rr6_butterfly.json` 的 4 个技能（bt_s1~bt_s4）、`timegap`、
  「幻影每硬币削减状态栈 1 层」「未受击幻影回补 +2」「形态切换给时隙」「HP 阈值补栈」
  —— **这些都是上一版臆造的**，真实 Imago 页面里没有对应描述。
* 「Boss 每回合 +8 SP」文档里已承认是自造 → 必须改名（如 `curriculum_boss_sp_recovery`）
  并按 curriculum 处理，不能写成游戏规则。
* `boss_hp_scale=0.5` 属于 curriculum 缩放，benchmark 必须标注为 scaled environment。
* 真实三套栈的获得/削减方式（Clash Win +5 / Clash Lose 减半）与攻击幻影的关系
  **仍需核实**（add 单位 9572~9574 的页面没找到，需要游戏内录像或后续抓取）。

---

## 9. 【B 级】其他机制缺口（影响实验可信度）

| 项 | 真实机制 | 当前 |
|---|---|---|
| Unbreakable Coin | 拼点失败不破坏而是 Crack，Coin Power 固定为 1（+1/−1），失败后仍可结算，混乱时取消 | 无 |
| Clashable Guard / Evade / Counter | 独立机制（Evade 可反复 reuse、Counter 反击） | 守望被简化成「不拼点、减伤 50%」 |
| 拼点平手 | 双方硬币一起破坏 | 已有（待校验） |
| Focused Encounter 改目标 | 「被指定的 Sinner 可以无视速度反向锁定该槽位」 | 用「速度更高才能改目标」近似 |
| SP 具体增减数值 | Sanity 页只说「赢拼点/击杀涨 SP，E.G.O/队友阵亡/沉沦掉 SP」 | `clash_win_sp_gain=1` 属 low confidence |
| Panic / Low Morale | SP ≤ −30 低士气、−45 恐慌、−45 且回合开始持有 E.G.O → 强制 E.G.O Corrosion 或 Panic 不行动；Sinner 下回合 SP 归 0 | 无 |

---

## 10. 结论与修改计划

### READY_FOR_SEARCH = **NO**

blocker（按优先级）：

1. E.G.O Coin Reuse 机制错误（污染实验核心假设）
2. 伤害公式错误（coin roll / 分段抗性 / 攻防等级 / 混乱）
3. 状态语义错误（Butterfly / Sinking / Echoes / Dazzle / Blessing / Sheut Fracture / Blue Sand）
4. 技能牌堆错误（3/2/1 + 抽空才洗）
5. E.G.O SP / 侵蚀 / Overclock 规则错误
6. clone / state hash 不足以支撑搜索（rng、deck_queue、深拷贝）
7. 合法目标被 `slot.cancelled` 错误限制
8. Boss 模型与真实战斗不符（需重做或明确标注为 synthetic）

### 计划修改的文件

```
tools/wiki_fetch.py                     # 新增（取证工具）
docs/audit_report.md                    # 本文件
docs/mechanics_notes.md                 # 按审计结论重写实现口径
docs/verification_checklist.md          # 重写，标注 verified/low/synthetic
docs/sources.md                         # 更新来源（wiki.gg + 抓取日期）

src/rr6sim/core/enums.py                # 扩展 Timing（coin_start/heads_hit/hit_after_clash_*/attack_end/combat_end）
src/rr6sim/core/skill.py                # Coin: unbreakable/cracked；移除 damage 依赖
src/rr6sim/core/context.py              # reuse 上下文、命中类型
src/rr6sim/core/effects.py              # reuse_coin（coin_index/max_reuse/condition/recursive）
src/rr6sim/core/engine.py               # 逐次判定 reuse、Unbreakable、侵蚀判定、合法目标、deck 抽取
src/rr6sim/core/damage.py               # 真实公式（coin roll + static/dynamic modifier）
src/rr6sim/core/status.py + data/statuses.json  # 状态语义重写 + confidence
src/rr6sim/core/state.py + unit.py      # transition_hash / observation_hash / 深拷贝
src/rr6sim/core/config.py               # 消融开关 + curriculum 开关重命名
src/rr6sim/content/loader.py            # deck 份数、unbreakable、provenance
src/rr6sim/env/*                        # action space 适配（Overclock、deck）
data/egos.json                          # 5 个 E.G.O 按 wiki 原文重录
data/identities.json                    # 7 人格 deck 3/2/1 + 状态机制修正
data/boss_rr6_butterfly.json            # 真实 Imago（或标注 synthetic 并另建真实版）
tests/unit/*                            # 新增/改写（见 §12 清单）
scripts/manual_line.py                  # 重新定义为 known-strategy regression test
README.md                               # 删除「收益结构指向沉沦→重投」的结论
```

### 测试清单（本次必须新增/改写）

1. skill deck 3/2/1 分布 + 抽空才洗 + fixed 可复现 + rng 同 seed 可复现
2. clone 深复制隔离（flags / deck_queue / Unit.state 嵌套 / statuses / slots / res）
3. RNG state 不同 → transition_hash 必须不同
4. deck_queue 不同 → transition_hash 必须不同
5. 混乱敌人仍可被单方面攻击
6. 不行动的幻影仍可被攻击
7. 低 SP 使用 E.G.O（觉醒/自动侵蚀）
8. Overclock（1.5× 代价）与「同回合不能重复使用同一 E.G.O」
9. Gregor 庄严哀悼 Coin Reuse（第 3 枚、SP ≥ 0、最多 5 次、每次 −2~6 SP）
10. Harmony Coin Reuse（第 3 枚、Heads Hit、HP ≥ 10%、自伤、最多 4 次）
11. Yi Sang 庄严哀悼 **没有** Coin Reuse，但有 5 枚 Unbreakable + Butterfly 结算
12. reuse 只重复正确的硬币（不是整个技能）
13. reuse 的硬币重新触发 On Hit（且 `Reuse -` 前缀只对被 reuse 的硬币生效）
14. reuse 是否允许递归（按原文「max per Skill」实现：计数封顶即停止）
15. Sinking Potency/Count 消耗与 99 上限
16. Sinking × 多次命中联动（含无 SP 单位 → Gloom 伤害）
17. Butterfly：Living/Departed 转换、攻击者回 SP、SP<0 时的 Gloom 伤害
18. 伤害公式：分段抗性、攻防等级 M 公式、混乱抗性替换、min 1 / 0.05×coin roll
19. deterministic replay 重跑一致
20. clone → 分支 A/B 互不污染

---

# 修复状态（本轮已实施）

> 本节记录审计发现的问题在代码里是否已经修好、用什么测试保证、以及仍然 blocking 的部分。

## 已修复（有对应测试）

| # | 问题 | 修复 | 测试 |
|---|---|---|---|
| 1 | Coin Reuse 机制臆造 | `reuse_coin`（指定硬币 / `max_reuse` 每技能 / 每次重判条件 / 可重新触发 On Hit / `reuse_only` 前缀）；`repeat_coin` 变成必须显式 `synthetic: true` 的 **synthetic** 效果 | `test_ego.py::TestCoinReuseMechanics`（5 项）+ `TestYiSangSolemnLament`（4 项） |
| 2 | 伤害公式错误 | `damage.py` 改为 `Coin Roll × (1+Static) × (1+Dynamic)`；分段抗性；`M = (Off−Def)/(|Off−Def|+25)`；拼点每 3 级 +1 威力；混乱替换物理抗性；取整/最低值规则 | `test_damage.py`（19 项） |
| 3 | Sinking 语义不完整 | `sinking_trigger`：有 SP 掉 SP、**无 SP 单位改为等强度 Gloom 伤害**（受罪孽抗性影响） | `test_statuses.py::TestSinking`（6 项） |
| 4 | Butterfly 语义完全错误 | `butterfly_trigger`（攻击者回 SP、SP<0 时的 Gloom 爆发、上限 30）+ `butterfly_turn_end`（Living↔Departed 转换）+ `inflict_butterfly`（每层独立判定 Living/Departed） | `test_statuses.py::TestButterfly`（5 项）+ `test_ego.py::test_coin5_spends_living_and_departed` |
| 5 | 技能牌堆错误 | 数据层 `{"sid": 份数}`（3/2/1）；抽空才 refill；fixed/rng 可复现 | `test_clone_isolation.py::TestDeck`（5 项） |
| 6 | E.G.O SP/侵蚀规则错误 | 去掉 SP 门槛；「扣到 ≤ −45 必定侵蚀」；SP<0 概率侵蚀；Overclock = 1.5×；同回合不可重复使用同一 E.G.O | `test_ego.py::TestEgoCostAndCorrosion`（6 项） |
| 7 | clone/hash 不足以支撑搜索 | `transition_hash`（含 rng_state、deck_queue/cursor、flags 深拷贝、counters）与 `observation_hash` 分离；`_deep()` 深复制作业 | `test_clone_isolation.py::TestCloneIsolation`（7 项）+ `TestHashSemantics`（6 项） |
| 8 | 合法目标被 `slot.cancelled` 限制 | 「会不会行动」与「能不能被打」分离（新增 `targetable`）；混乱 / 不行动的敌人仍是合法目标 | `test_targets.py`（新增 4 项） |
| 9 | Unbreakable Coin 缺失 | 拼点失败 → Cracked（威力固定 +1/−1）并在失败后结算；HP 阈值转 Unbreakable | `test_damage.py::test_unbreakable_coin_becomes_cracked_not_destroyed` |
| 10 | Boss 机制臆造 | 按 wiki 原文重录 Imago：HP 25616、4 段混乱阈值、12 技能、三套时间栈（含「幻影被击中 → 本体失去对应栈」）、三回合技能循环、333 Shield 幻影 | `test_butterfly_boss.py`（15 项） |
| 11 | 「Boss 每回合 +8 SP」被伪装成规则 | 该被动已从数据中删除（真实 Imago 没有此机制） | `test_butterfly_boss.py::test_boss_has_no_sanity` 等 |
| 12 | 未实现机制静默失真 | 新增 `not_implemented` handler：每次触发写日志并计入 `counters["not_implemented"]` | `scripts/manual_line.py` 报告该计数 |
| 13 | README 的「沉沦→重投」结论 | 已删除，改为 prototype 声明 + blocker 列表 | — |

## 仍然 blocking（READY_FOR_SEARCH = NO 的直接原因）

1. **7 个人格的数据仍是 synthetic 占位**（`data/identities.json`）。
   真实 RR6 需要按每个人格页录入技能 power/coin/状态施加/被动。
   → 直接决定「沉沦 setup 能不能成立、Coin Reuse 能不能配合」。
2. **Poise / 暴击**未实现。Imago 的多个技能（`Anitya` / `Skypiercer` / `Smite the Wicked`）
   伤害与暴击强相关，缺失会让 Boss 威胁与「In the Present」的收益都失真。
3. **Imago 技能的「按 In the Past/Present/Future 栈提升伤害」**未实现
   （当前为 `not_implemented`）。这是「靠幻影控制本体输出」这一核心博弈的一半。
4. **Burn / Bleed 的完整口径**未实现（Imago 的主循环是 Burn/Bleed），
   会影响伤害量级与 SP 压力。
5. **E.G.O 侵蚀形态的效果文本**只有基础数据。
6. **幻影蝶 Section 5 版本**（id 9572~9574）的数据未找到页面，当前用 Section 2~4 版本近似。

## 修复后的诚实基准（**不是**策略结论）

用真实机制 + synthetic 人格数据（`boss_hp_scale = 0.5`，即 scaled environment）：

```
known line: ally_win kill_turn=13   （not_implemented 触发 142 次）
greedy    : ally_win kill_turn=15
```

* 这两个数字**不能**用来论证「沉沦 + 重投是最优策略」：
  人格数据是占位的，且仍有大量真实机制未实现。
* 消融开关确实生效：关闭 Coin Reuse → `reuse_count = 0`；
  关闭「沉沦 → Gloom 伤害」→ `sinking_gloom_damage = 0`。
* 上一版 README 里「Greedy 20 回合打不完、known line 7 回合」的对比，
  是建立在「沉沦越高 → 全硬币重投」这个臆造机制上的，**已作废**。

## 判定

**READY_FOR_SEARCH = NO**

理由（对应用户给出的四条前置条件）：

| 前置条件 | 状态 |
|---|---|
| 状态 clone/hash 没问题 | ✅ 已修好（含 RNG / 牌堆 / 深拷贝，有测试） |
| 动作合法性没问题 | ✅ 已修好（混乱 / 不行动目标可攻击，有测试） |
| 核心 E.G.O Coin Reuse 没问题 | ✅ 机制已按 wiki 原文实现并有测试；⚠️ 但侵蚀形态效果文本仍缺 |
| deck 没问题 | ✅ 3/2/1 + 抽空才洗（有测试） |
| sinking 基本没问题 | ✅ 对有无 SP 单位都正确；⚠️ Burn/Bleed 口径缺失影响沉沦队的实际强度 |
| 人格/敌人数据可信 | ❌ **7 个人格是 synthetic 占位**；Imago 的 Poise/暴击与按栈加成伤害未实现 |

即：**引擎层的规则已经可信到可以开始写搜索，但数据层还不足以让搜索结果有意义。**
