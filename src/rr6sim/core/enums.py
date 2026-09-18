"""基础枚举与常量。

所有枚举都继承 ``str``，因此可以直接出现在 JSON/YAML 数据文件里，
不需要额外的序列化层（见 ``data/*.json`` 的 ``source/confidence`` 约定）。
"""

from __future__ import annotations

from enum import Enum


class Sin(str, Enum):
    """七大罪孽。"""

    WRATH = "wrath"
    LUST = "lust"
    SLOTH = "sloth"
    GLUTTONY = "gluttony"
    GLOOM = "gloom"
    PRIDE = "pride"
    ENVY = "envy"


SIN_CN = {
    Sin.WRATH: "暴怒",
    Sin.LUST: "色欲",
    Sin.SLOTH: "怠惰",
    Sin.GLUTTONY: "暴食",
    Sin.GLOOM: "忧郁",
    Sin.PRIDE: "傲慢",
    Sin.ENVY: "嫉妒",
}


class DamageType(str, Enum):
    """物理伤害类型（抗性分三类）。"""

    SLASH = "slash"
    PIERCE = "pierce"
    BLUNT = "blunt"


DAMAGE_TYPE_CN = {
    DamageType.SLASH: "斩击",
    DamageType.PIERCE: "突刺",
    DamageType.BLUNT: "打击",
}


class CoinKind(str, Enum):
    """硬币种类。

    POSITIVE：正面时获得硬币威力（+coin power），精神力越高越容易正面。
    NEGATIVE：反面时获得硬币威力，精神力越低越容易反面（见 rng / sanity 公式）。
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"


class Side(str, Enum):
    ALLY = "ally"
    ENEMY = "enemy"


class SlotKind(str, Enum):
    """行动槽本回合的处置方式。"""

    SKILL = "skill"
    EGO = "ego"
    GUARD = "guard"  # 守备（本实验只做基础的格挡/闪避占位）


class Form(str, Enum):
    """罗生蝶形态：由过去/现在/未来三套状态栈中最高的一个决定。"""

    NEUTRAL = "neutral"
    PAST = "past"
    PRESENT = "present"
    FUTURE = "future"


class TimeType(str, Enum):
    """幻影 / 状态栈的时间类型。"""

    PAST = "past"
    PRESENT = "present"
    FUTURE = "future"


class Timing(str, Enum):
    """事件时点。计划书 §7 的时点表，全部用字符串表达以便数据文件引用。"""

    BATTLE_START = "battle_start"
    TURN_START = "turn_start"
    SPEED_ROLL = "speed_roll"
    SKILL_CHOICES_READY = "skill_choices_ready"
    COMBAT_START = "combat_start"
    BEFORE_CLASH = "before_clash"
    ON_USE = "on_use"
    CLASH_WIN = "on_clash_win"
    CLASH_LOSE = "on_clash_lose"
    BEFORE_ATTACK = "before_attack"
    COIN_START = "coin_start"
    BEFORE_COIN = "before_coin"
    COIN_HEADS = "on_coin_heads"
    COIN_TAILS = "on_coin_tails"
    HEADS_HIT = "heads_hit"
    TAILS_HIT = "tails_hit"
    HIT_AFTER_CLASH_WIN = "hit_after_clash_win"
    HIT_AFTER_CLASH_LOSE = "hit_after_clash_lose"
    ON_HIT_WITHOUT_CRACKING = "on_hit_without_cracking"
    COIN_HIT = "on_hit"
    ON_CRIT = "on_crit"
    COIN_MISS = "on_coin_miss"
    AFTER_COIN = "after_coin"
    CURRENT_COIN_ATTACK_END = "current_coin_attack_end"
    AFTER_ATTACK = "after_attack"
    ATTACK_END = "attack_end"
    COMBAT_END = "combat_end"
    ON_KILL = "on_kill"
    ON_STAGGER = "on_stagger"
    ON_DEATH = "on_death"
    FORCE_STAGGER = "on_force_stagger"
    TURN_END = "turn_end"
    ON_FORM_CHANGE = "on_form_change"
    ON_TARGETED = "on_targeted"
    ON_STACK_THRESHOLD = "on_stack_threshold"
    ON_HP_THRESHOLD = "on_hp_threshold"


class Phase(str, Enum):
    """环境阶段。"""

    PLANNING = "planning"  # 自回归构造本回合计划
    TERMINAL = "terminal"


class TargetMode(str, Enum):
    """攻击模式。"""

    CLASH = "clash"
    ONE_SIDED = "one_sided"


class Outcome(str, Enum):
    ONGOING = "ongoing"
    ALLY_WIN = "ally_win"
    ALLY_LOSE = "ally_lose"


# 目标 token（数据文件里用字符串引用单位集合）
TARGET_SELF = "self"
TARGET_OTHER = "other"  # 技能上下文=目标单位；状态上下文=施加者/对手
TARGET_ALL_ALLIES = "all_allies"
TARGET_ALL_ENEMIES = "all_enemies"
TARGET_BOSS = "boss"
TARGET_RANDOM_ALLY = "random_ally"
TARGET_RANDOM_ENEMY = "random_enemy"
TARGET_LOWEST_HP_ALLY = "lowest_hp_ally"
TARGET_TARGET_ALLIES = "target_allies"  # 目标单位所在阵营
