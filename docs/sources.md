# 数据来源与取证方法

> 审计结论与修复状态见 `docs/audit_report.md`；实现口径见 `docs/mechanics_notes.md`；
> 逐条置信度台账见 `docs/verification_checklist.md`。

## 1. 取证通道（重要）

本项目上一版因为 `limbuscompany.huijiwiki.com` 返回 **403**（含 `api.php`），
最终把「按记忆重建的近似值」当成了数据，导致大量机制是臆造的（详见 audit report）。

本轮改用 **英文 Wiki（wiki.gg）**，并且解决了 Cloudflare 拦截：

| 方式 | 结果 |
|---|---|
| 直连 `limbuscompany.wiki.gg/wiki/...` | ❌ 403（Cloudflare 挑战页） |
| 直连 `limbuscompany.wiki.gg/api.php?...` | ❌ 403 |
| `api.allorigins.win` 代理 | ❌ 522 |
| **`r.jina.ai` 代理 MediaWiki API** | ✅ 200，返回完整 wikitext |

用法（已封装为工具）：

```bash
python3 tools/wiki_fetch.py search "Coin Reuse"
python3 tools/wiki_fetch.py category "E.G.O with Coin Reuse"
python3 tools/wiki_fetch.py page "Solemn Lament Gregor" --raw
python3 tools/wiki_fetch.py page "Sanity" --raw
```

* 抓取缓存：`_sources/`（已 gitignore；内含 `fetched_at` 与来源 URL）
* 代理 URL 必须**整体 percent-encode**，否则 `r.jina.ai` 会把参数当成自己的参数报 400

## 2. 本轮抓取并据以修改代码的页面

| 页面 | 用途 |
|---|---|
| `Battles` | 回合流程、Skill Tags 全表、Skill Deck 3/2/1、Unbreakable Coin、Stagger、攻防等级、Parts |
| `Sanity` | `H = 50 + SP`、SP 区间、Panic/Low Morale、无 SP 单位、沉沦对无 SP 单位的处理 |
| `Damage Formula` | 真实伤害公式（Coin Roll / Static / Dynamic、分段抗性、攻防等级、混乱） |
| `Sinking` | Sinking / Butterfly（The Living & The Departed）/ Echoes of the Manor / Dazzle / Sheut Fracture / Blue Sand / Blessing |
| `E.G.O/Gameplay` | SP 消耗、觉醒/侵蚀判定、Overclock 1.5×、同回合不可重复使用 |
| `Category:E.G.O with Coin Reuse` | **Coin Reuse 的真实成员名单** |
| `Solemn Lament Yi Sang` / `Solemn Lament Gregor` / `Harmony Sinclair` | 3 个核心 E.G.O 的完整文本（含 reuse 条件） |
| `Bygone Days Yi Sang` / `Bygone Days Ishmael` / `Rime Shank Rodion` | 其余 3 个实验用 E.G.O |
| `Butterfly of Entangled Lives 羅生蝶/Enemy/Butterfly of Entangled Lives::Imago` | Boss 真实数值、12 技能、passive、技能循环、Choice Event |
| `Illusory Butterfly of Entangled Lives::The Past/Present/The Future` | 三幻影蝶（333 Shield / Eclosion） |
| `Line 6: Maru no Uchi no Sanzu no Kawa` | Section/Station 结构、Section 5 开局继承规则、Chain Battle |
| `List of Enemies` / `search` | 页面名解析（罗生蝶 = Butterfly of Entangled Lives 羅生蝶） |

## 3. 名称对照（社区简称 → 正式条目）

| 计划书简称 | 英文 Wiki 条目 | 备注 |
|---|---|---|
| 蝶箱 | `Lobotomy E.G.O::Solemn Lament Yi Sang` | E.G.O：`Solemn Lament Yi Sang`、`Bygone Days Yi Sang` |
| 目灯虫 | `Lobotomy E.G.O::Lamp Gregor` | E.G.O：`Solemn Lament Gregor` |
| 管家浮 | `Wuthering Heights Butler Faust` | 相关状态：Echoes of the Manor |
| 花札玛 | 待核实（计划书写「定事务所代表」，Wiki 有 `Jeong's Office Rep Ishmael`） | E.G.O：`Bygone Days Ishmael` |
| 乐队辛 | 待核实（计划书写「流浪乐队头目」） | E.G.O：`Harmony Sinclair` |
| LCA 奥 | `LCA Udjat Vanguard Team 3 Leader Outis` | 相关状态：Sheut Fracture / Blue Sand |
| 绝望罗 | `Lobotomy E.G.O::The Sword Sharpened with Tears Rodion` | E.G.O：`Rime Shank Rodion`（= 冰结之爪） |
| 罗生蝶 | `Butterfly of Entangled Lives 羅生蝶`（Abnormality 页）→ 战斗页 `.../Enemy/Butterfly of Entangled Lives::Imago` | Section 5 / Station 8「Advent」 |
| 三幻影 | `Illusory Butterfly of Entangled Lives::The Past / The Present / The Future` | hp=1 + 333 Shield |
| 庄严哀悼 | `Solemn Lament`（= 亡蝶葬仪 `Funeral of the Dead Butterflies` 系） | **李箱没有 Coin Reuse，格里高尔有** |
| 和声 | `Harmony`（Abnormality: `Singing Machine`） | Coin Reuse |
| 往昔 | `Bygone Days` | 无 Coin Reuse |
| 冰结之爪 | `Rime Shank` | 无 Coin Reuse |

## 4. 版本快照

| 项 | 值 |
|---|---|
| 资料快照日期 | 2026-09-18 |
| 游戏版本 | Ver. 1.114.0（计划书 §1 记录） |
| 主数据源 | `limbuscompany.wiki.gg`（CC BY-SA；本仓库只保存规范化数值与短引用） |
| 备用源 | 游戏内文本、官方公告、可靠实战录像（用于校验 §B/§C 项） |

> Wiki 内容通常按 CC BY-SA 授权。本仓库只保存训练所需的规范化数值、
> 机制描述与短引用，不搬运图片、语音等素材。
