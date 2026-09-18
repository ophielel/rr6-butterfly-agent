"""状态（buff / debuff）定义与实例。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StatusSpec:
    """一种状态的静态定义。

    potency = 强度，count = 层数（与游戏内「强度 / 层数」对应）。
    有些状态只有层数（如「蝶」「时隙」），有些只有强度。
    """

    key: str
    name_cn: str
    name_en: str = ""
    has_potency: bool = False
    has_count: bool = False
    #: 回合结束时层数减少量（沉沦/破裂/出血这类「每次触发减 1 层」的状态这里填 0，
    #: 因为它们的层数是在命中触发时减少的，而不是回合结束）
    turn_end_count_decay: int = 0
    turn_end_potency_decay: int = 0
    #: 受到伤害的倍率修正（每层 / 每点强度）
    damage_taken_mult_per_count: float = 0.0
    damage_taken_mult_per_potency: float = 0.0
    #: 造成伤害的倍率修正（每层）
    damage_dealt_mult_per_count: float = 0.0
    #: 拼点威力修正（每层）
    clash_power_per_count: int = 0
    #: 攻击等级修正（每层）
    offense_level_per_count: int = 0
    #: 触发时点钩子，格式与技能效果一致：[{"when": "on_hit", "if": {...}, "kind": ...}]
    hooks: list = field(default_factory=list)
    description: str = ""
    source: str = ""
    confidence: str = "unverified"


@dataclass
class StatusStack:
    """状态实例：某个单位身上的某个状态。"""

    key: str
    potency: int = 0
    count: int = 0

    def is_empty(self) -> bool:
        return self.potency <= 0 and self.count <= 0

    def copy(self) -> "StatusStack":
        return StatusStack(self.key, self.potency, self.count)

    def to_dict(self) -> dict:
        return {"key": self.key, "potency": self.potency, "count": self.count}

    @staticmethod
    def from_dict(d: dict) -> "StatusStack":
        return StatusStack(d["key"], int(d.get("potency", 0)), int(d.get("count", 0)))


class StatusRegistry:
    """状态注册表。数据文件加载后会注册到这里。"""

    def __init__(self) -> None:
        self._specs: dict[str, StatusSpec] = {}

    def register(self, spec: StatusSpec) -> None:
        self._specs[spec.key] = spec

    def get(self, key: str) -> StatusSpec:
        spec = self._specs.get(key)
        if spec is None:
            # 未登记的状态退化为「纯强度+纯层数、无钩子」，保证模拟器不会因为
            # 数据缺失直接崩掉（但会在 replay 里留下 warning）。
            spec = StatusSpec(key=key, name_cn=key, has_potency=True, has_count=True,
                              confidence="unregistered")
            self._specs[key] = spec
        return spec

    def keys(self) -> list:
        return sorted(self._specs)

    def to_dict(self) -> dict:
        out = {}
        for k, s in self._specs.items():
            out[k] = {
                "name_cn": s.name_cn,
                "name_en": s.name_en,
                "has_potency": s.has_potency,
                "has_count": s.has_count,
                "turn_end_count_decay": s.turn_end_count_decay,
                "turn_end_potency_decay": s.turn_end_potency_decay,
                "damage_taken_mult_per_count": s.damage_taken_mult_per_count,
                "damage_taken_mult_per_potency": s.damage_taken_mult_per_potency,
                "damage_dealt_mult_per_count": s.damage_dealt_mult_per_count,
                "hooks": s.hooks,
                "description": s.description,
                "source": s.source,
                "confidence": s.confidence,
            }
        return out

    @staticmethod
    def from_dict(d: dict) -> "StatusRegistry":
        reg = StatusRegistry()
        for k, v in d.items():
            reg.register(StatusSpec(
                key=k,
                name_cn=v.get("name_cn", k),
                name_en=v.get("name_en", ""),
                has_potency=v.get("has_potency", False),
                has_count=v.get("has_count", False),
                turn_end_count_decay=v.get("turn_end_count_decay", 0),
                turn_end_potency_decay=v.get("turn_end_potency_decay", 0),
                damage_taken_mult_per_count=v.get("damage_taken_mult_per_count", 0.0),
                damage_taken_mult_per_potency=v.get("damage_taken_mult_per_potency", 0.0),
                damage_dealt_mult_per_count=v.get("damage_dealt_mult_per_count", 0.0),
                clash_power_per_count=v.get("clash_power_per_count", 0),
                offense_level_per_count=v.get("offense_level_per_count", 0),
                hooks=list(v.get("hooks", [])),
                description=v.get("description", ""),
                source=v.get("source", ""),
                confidence=v.get("confidence", "unverified"),
            ))
        return reg


#: 常用状态 key（避免各处硬编码字符串拼错）
SINKING = "sinking"
BUTTERFLY = "butterfly"
LIVING_BUTTERFLY = "living_butterfly"
DEAD_BUTTERFLY = "dead_butterfly"
ECHO = "manor_echo"
DAZZLE = "dazzle"
HIKARI = "hikari"
SHADOW_CRACK = "shadow_crack"
TIMEGAP = "timegap"
PAST = "past"
PRESENT = "present"
FUTURE = "future"
STRONG = "strong"
FRAGILE = "fragile"
OFFENSE_UP = "offense_level_up"
OFFENSE_DOWN = "offense_level_down"
CLASH_POWER_UP = "clash_power_up"
PROTECT = "protect"
RUPTURE = "rupture"
BLEED = "bleed"
BURN = "burn"
TREMOR = "tremor"
DESPAIR = "despair"
BLESSING = "blessing"
