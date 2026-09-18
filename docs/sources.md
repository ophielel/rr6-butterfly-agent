# 数据来源与置信度（M0：数据冻结）

> 计划书 §4 / §M0：每个条目保存来源 URL、录入日期、游戏版本；所有数字都能追溯来源。

## 采集环境说明（重要）

本机访问 `limbuscompany.huijiwiki.com` 一律返回 **HTTP 403**（尝试过浏览器 UA、
`api.php` 接口，均被拒）。因此**没有抓到任何 Wiki 结构化数据**。

* `data/*.json` 里的数值是**按游戏机制结构 + 记忆重建的近似值**，
  机制（时点、每硬币触发、状态语义、拼点结构）是保真的，
  但**具体数字与技能效果文本必须逐条对照游戏内文本校验**。
* 每个数据文件都有 `_meta`（来源/假设/置信度），每个条目也有 `source` / `confidence`。
* 校验清单见 `docs/verification_checklist.md`；校验后请把 `confidence` 改成
  `verified` 并填上实际来源（截图 / 游戏内文本 / Wiki 页面快照）。

## 版本快照

| 项 | 值 |
|---|---|
| 资料快照日期 | 2026-09-18 |
| 游戏版本 | Ver. 1.114.0（计划书 §1 记录） |
| Wiki 可达性 | ❌ 403 |
| 官方公告 | https://steamcommunity.com/app/1973530/announcements/（未抓取） |

## 数据文件

| 文件 | 内容 | 置信度 | 主要来源 |
|---|---|---|---|
| `data/statuses.json` | 状态定义与触发钩子 | 中（语义）/ 低（数值倍率） | 技能与拼点、蝶、各人格页面 |
| `data/identities.json` | 7 个人格的技能组 / 被动 / 专属资源 | 低（数值） | 各人格页面（见下表 URL） |
| `data/egos.json` | 6 个重点 E.G.O（觉醒 + 侵蚀 + 抗性覆盖） | 低（数值） | 各 E.G.O 页面 |
| `data/boss_rr6_butterfly.json` | 罗生蝶本体 + 三幻影 + 形态/阈值 | 低（数值）/ 中（结构） | 折射轨道6号线-第五区段 |

## 人格 / E.G.O 条目来源

| 条目 | Wiki 页面 |
|---|---|
| 蝶箱（李箱 脑叶公司 E.G.O::庄严哀悼） | https://limbuscompany.huijiwiki.com/wiki/李箱脑叶公司E.G.O::庄严哀悼 |
| 目灯虫（格里高尔 脑叶公司 E.G.O::目灯） | https://limbuscompany.huijiwiki.com/wiki/格里高尔脑叶公司E.G.O:目灯 |
| 管家浮（浮士德 呼啸山庄管家） | https://limbuscompany.huijiwiki.com/wiki/浮士德呼啸山庄管家 |
| 花札玛（以实玛利 定事务所代表） | https://limbuscompany.huijiwiki.com/wiki/以实玛利定事务所代表 |
| 乐队辛（辛克莱 流浪乐队头目） | https://limbuscompany.huijiwiki.com/wiki/辛克莱流浪乐队头目 |
| LCA 奥（奥提斯 LCA 瓦吉特先锋三队队长） | https://limbuscompany.huijiwiki.com/wiki/奥提斯LCA瓦吉特先锋三队队长 |
| 绝望罗（罗佳 脑叶公司 E.G.O::泪锋之剑） | https://limbuscompany.huijiwiki.com/wiki/罗佳脑叶公司E.G.O::泪锋之剑 |
| 庄严哀悼 - 李箱 | https://limbuscompany.huijiwiki.com/wiki/庄严哀悼-李箱 |
| 庄严哀悼 - 格里高尔 | https://limbuscompany.huijiwiki.com/wiki/庄严哀悼-格里高尔 |
| 往昔 - 李箱 | https://limbuscompany.huijiwiki.com/wiki/往昔-李箱 |
| 往昔 - 以实玛利 | https://limbuscompany.huijiwiki.com/wiki/往昔-以实玛利 |
| 和声 - 辛克莱 | https://limbuscompany.huijiwiki.com/wiki/和声-辛克莱 |
| 冰结之爪 - 罗佳 | https://limbuscompany.huijiwiki.com/wiki/冰结之爪-罗佳 |
| 罗生蝶 | https://limbuscompany.huijiwiki.com/wiki/罗生蝶 |
| RR6 第五区段 | https://limbuscompany.huijiwiki.com/wiki/折射轨道6号线-第五区段 |

## 玩法机制来源

| 机制 | 页面 |
|---|---|
| 技能 / 硬币 / 拼点 / 回合流程 | https://limbuscompany.huijiwiki.com/wiki/技能与拼点 |
| 攻击等级 | https://limbuscompany.huijiwiki.com/wiki/攻击等级 |
| 伤害计算 | https://limbuscompany.huijiwiki.com/wiki/伤害计算 |
| 速度值与行动顺序 | https://limbuscompany.huijiwiki.com/wiki/速度值 |
| E.G.O 规则（SP 消耗 / 侵蚀 / 抗性覆盖） | https://limbuscompany.huijiwiki.com/wiki/E.G.O |
| 特殊状态「蝶」 | https://limbuscompany.huijiwiki.com/wiki/蝶 |

## 结构化数据表（校验时优先使用）

* 人格总表：https://limbuscompany.huijiwiki.com/wiki/人格
* E.G.O 总表：https://limbuscompany.huijiwiki.com/wiki/E.G.O
* 人格结构化数据：https://limbuscompany.huijiwiki.com/wiki/Data:Identitychoose.tabx
* E.G.O 结构化数据：https://limbuscompany.huijiwiki.com/wiki/Data:Egochoose.tabx
* 人格被动：https://limbuscompany.huijiwiki.com/wiki/Data:Identitypassive.tabx
* 状态/关键词：https://limbuscompany.huijiwiki.com/wiki/Data:Buffchoose.tabx
* 敌方基础数据：https://limbuscompany.huijiwiki.com/wiki/Data:Enemy.tabx

> Wiki 内容通常按 CC BY-SA 4.0 授权。本仓库只保存训练所需的规范化数值与短描述，
> 不搬运图片、语音等素材；引用时请保留来源与许可证信息。

## 许可证与命名注意

* 社区简称存在歧义（“圣宣 / 庄严哀悼 / Solemn Lament”）。
  数据里统一使用 `solemn_lament_*` 作为 key，并在 `name` 字段写标准中文名，
  不要用简称当唯一键（计划书 §2）。
* 严禁把不同补丁时期的数据混在一起：若要复现“六号线刚开放时”的历史环境，
  请另建 `data/` 快照目录并记录版本号，`Content(data_dir=...)` 支持切换。
