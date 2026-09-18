"""实验配置：所有会改变结算的开关与常数集中在这里。

设计原则（计划书 §9 / §21 / §17）：
* 「无限罪孽资源」≠「无代价」——SP、侵蚀、E.G.O 抗性覆盖全部保留。
* 所有用于消融实验的开关都在这里，不在模拟器里硬编码。
* ``config_hash`` 会进 replay，保证「这条录像是在哪套规则下产生的」可追溯。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields, asdict


@dataclass
class SimConfig:
    # ---- 随机性阶段（计划书 §10）----
    #: always_heads / always_tails / script / rng
    coin_mode: str = "rng"
    #: fixed / rng
    speed_mode: str = "rng"
    #: fixed / rng  （技能抽取：fixed = 每回合固定牌序）
    skill_draw_mode: str = "rng"
    #: rng / greedy / script
    boss_ai: str = "script"
    #: 手工硬币脚本（coin_mode == "script" 时使用），按顺序取用
    coin_script: list = field(default_factory=list)

    # ---- 数值规则 ----
    #: 精神力对硬币正面的影响：P(正面) = 0.5 + SP * san_per_point
    san_per_point: float = 0.01
    #: 攻击等级每高于对方防御等级 1 点，伤害 ±3%
    level_diff_damage_per_level: float = 0.03
    #: 拼点时攻击等级差的影响（每 3 点差 +1 威力）。默认 0（保守，待游戏内校验）
    clash_level_bonus_per_3: float = 0.0
    #: 拼点胜利后，已翻出的硬币正反面结果是否沿用到伤害阶段
    clash_coin_carryover: bool = True
    #: 拼点平手：双方硬币一起破坏
    clash_tie_destroys_both: bool = True
    #: 硬币正面（或负硬币反面）时，硬币威力是否也计入该硬币的伤害
    #: True: 伤害 = 硬币伤害 + 硬币威力；False: 伤害只看硬币伤害值
    coin_power_adds_damage: bool = True
    #: 拼点模型：advance（双方每轮各消耗一枚硬币，硬币多者占优）
    #:          reflex（胜者保留当前硬币续拼，高威力少硬币占优）
    clash_model: str = "advance"
    #: 只有相互指定同一个槽位才会拼点
    clash_same_slot: bool = True
    #: 改目标需要速度高于被保护的我方槽位
    enforce_redirect_speed: bool = True
    #: 拼点胜利方的 SP 变化 / 失败方
    clash_win_sp_gain: int = 1
    clash_lose_sp_loss: int = 0
    #: 我方单位阵亡时其他我方单位的 SP 变化
    ally_death_sp_loss: int = -10
    #: 混乱（气绝）状态下受到伤害的倍率
    stagger_damage_taken_mult: float = 1.5
    #: 混乱持续：本回合剩余 + 下一回合
    stagger_lasts_next_turn: bool = True
    #: 守备（格挡）减伤
    guard_damage_mult: float = 0.5

    # ---- 资源 ----
    sin_resources: str = "infinite"  # infinite / finite
    corrosion_enabled: bool = True
    ego_resistance_override: bool = True
    ego_passives_enabled: bool = True

    # ---- 消融开关（计划书 §17）----
    sinking_enabled: bool = True
    butterfly_special_sinking: bool = True  # 「蝶」的额外沉沦/HP 伤害
    #: 重复投掷 / 追加硬币的总开关（消融 E）
    repeat_coin_enabled: bool = True
    #: 单枚硬币最多重复投掷几次（防无限递归的安全阀）
    max_repeat_per_coin: int = 4
    disabled_identities: list = field(default_factory=list)
    disabled_egos: list = field(default_factory=list)

    # ---- 罗生蝶专用 ----
    #: 幻影受到的伤害向本体转移的比例
    phantom_damage_transfer: float = 1.0
    #: 幻影整回合未被作为主要目标攻击时，对应状态栈回补量
    phantom_restore_amount: int = 2
    #: 命中幻影时，每枚硬币削减对应状态栈的量
    phantom_stack_decay_per_coin: int = 1
    #: 本体 HP 跨过每个阈值时，三套状态栈补充量
    hp_threshold_stack_bonus: int = 2
    #: 形态切换时获得的「时隙」层数
    form_switch_timegap: int = 2
    #: 幻影被打空 HP 后停止回补的回合数
    phantom_broken_turns: int = 1
    #: 幻影是否主动攻击（课程 0/1 可以关掉）
    phantom_acts: bool = True
    #: 状态钩子总开关（消融 F/G 用）
    status_hooks_enabled: bool = True
    #: RR6 前三段「禁用被动」选择（配置项，不硬编码）
    disabled_rr6_passives: list = field(default_factory=list)
    #: 第五区段事件增益
    encounter_buffs: dict = field(default_factory=dict)
    #: 初始 SP / HP 覆盖（课程 0~6 用来固定起始状态）
    ally_sp: int = 30
    ally_hp_pct: float = 1.0
    boss_hp: int = 25616
    #: wiki 记录的 25616 是绝对数值；本实验默认按 0.25 缩放，使 7 人单槽的
    #: 回合尺度落在 8~20 回合（便于搜索 / 训练）。设为 1.0 即完全按 wiki 数值。
    boss_hp_scale: float = 0.5

    # ---- 奖励（计划书 §14）----
    reward_kill: float = 100.0
    reward_turn_penalty: float = -3.0
    reward_defeat: float = -100.0
    reward_hp_shaping: float = 0.0  # 默认 0：不给 HP shaping，避免污染实验

    # ---- 其它 ----
    max_turns: int = 20
    deterministic: bool = False  # 一键把所有随机性关掉

    # ------------------------------------------------------------------
    def normalized(self) -> "SimConfig":
        cfg = SimConfig(**asdict(self))
        if cfg.deterministic:
            cfg.coin_mode = "script" if cfg.coin_script else "always_heads"
            cfg.speed_mode = "fixed"
            cfg.skill_draw_mode = "fixed"
            cfg.boss_ai = "script"
        if not cfg.repeat_coin_enabled:
            # 消融 E：关闭「重复硬币」——由效果层统一过滤，见 effects.py
            pass
        return cfg

    def to_dict(self) -> dict:
        d = asdict(self)
        d["encounter_buffs"] = dict(self.encounter_buffs)
        return d

    def hash(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]

    # 便捷构造
    @staticmethod
    def from_dict(d: dict) -> "SimConfig":
        known = {f.name for f in fields(SimConfig)}
        kw = {k: v for k, v in (d or {}).items() if k in known}
        return SimConfig(**kw)
