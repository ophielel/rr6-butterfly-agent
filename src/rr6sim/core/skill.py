"""技能 / 硬币 / E.G.O 数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import CoinKind, DamageType, Sin, SlotKind


def bindings(effects: list, when: str) -> list:
    """从效果列表里筛出指定时点的效果。

    效果 dict 的 ``when`` 字段就是绑定时点；没有 ``when`` 的效果默认绑在
    ``on_hit``（对硬币而言）等调用方指定的默认时点。
    """
    out = []
    for e in effects or ():
        if isinstance(e, dict):
            if e.get("when") == when:
                out.append(e)
    return out


@dataclass
class Coin:
    """一枚硬币。

    power  —— 拼点威力（正面硬币正面时 +power，负面硬币反面时 +power）
    damage —— 该硬币命中时的基础伤害值
    effects—— 绑定时点的效果列表
    """

    kind: CoinKind = CoinKind.POSITIVE
    power: int = 0
    damage: int = 0
    effects: list = field(default_factory=list)
    reusable: bool = False  # 被「重复投掷」时是否可再次触发命中效果（默认可以）

    def favorable(self, heads: bool) -> bool:
        """该正面/反面结果是否对硬币有利。"""
        return heads if self.kind is CoinKind.POSITIVE else not heads

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "power": self.power,
            "damage": self.damage,
            "effects": self.effects,
            "reusable": self.reusable,
        }

    @staticmethod
    def from_dict(d: dict) -> "Coin":
        return Coin(
            kind=CoinKind(d.get("kind", "positive")),
            power=int(d.get("power", 0)),
            damage=int(d.get("damage", 0)),
            effects=list(d.get("effects", [])),
            reusable=bool(d.get("reusable", False)),
        )


@dataclass
class Skill:
    """一个可执行的技能（普通技能 / 守备 / E.G.O 觉醒侵蚀形态都用它表示）。"""

    sid: str
    name: str
    sin: Sin
    damage_type: DamageType
    base_power: int
    coins: list = field(default_factory=list)
    offense_level_mod: int = 0
    effects: list = field(default_factory=list)  # 技能级钩子（on_use / before_attack / ...）
    weight: int = 1
    target_count: int = 1
    owner: str = ""  # 人格 / E.G.O 归属
    sp_cost: int = 0
    kind: SlotKind = SlotKind.SKILL
    tags: list = field(default_factory=list)
    description: str = ""
    source: str = ""
    confidence: str = "unverified"

    @property
    def coin_count(self) -> int:
        return len(self.coins)

    def to_dict(self) -> dict:
        return {
            "sid": self.sid,
            "name": self.name,
            "sin": self.sin.value,
            "damage_type": self.damage_type.value,
            "base_power": self.base_power,
            "coins": [c.to_dict() for c in self.coins],
            "offense_level_mod": self.offense_level_mod,
            "effects": self.effects,
            "weight": self.weight,
            "target_count": self.target_count,
            "owner": self.owner,
            "sp_cost": self.sp_cost,
            "kind": self.kind.value,
            "tags": self.tags,
            "description": self.description,
            "source": self.source,
            "confidence": self.confidence,
        }

    @staticmethod
    def from_dict(d: dict) -> "Skill":
        return Skill(
            sid=d["sid"],
            name=d.get("name", d["sid"]),
            sin=Sin(d.get("sin", "wrath")),
            damage_type=DamageType(d.get("damage_type", "slash")),
            base_power=int(d.get("base_power", 0)),
            coins=[Coin.from_dict(c) for c in d.get("coins", [])],
            offense_level_mod=int(d.get("offense_level_mod", 0)),
            effects=list(d.get("effects", [])),
            weight=int(d.get("weight", 1)),
            target_count=int(d.get("target_count", 1)),
            owner=d.get("owner", ""),
            sp_cost=int(d.get("sp_cost", 0)),
            kind=SlotKind(d.get("kind", "skill")),
            tags=list(d.get("tags", [])),
            description=d.get("description", ""),
            source=d.get("source", ""),
            confidence=d.get("confidence", "unverified"),
        )


@dataclass
class Ego:
    """E.G.O：觉醒 / 侵蚀两套形态，以及使用后的罪孽抗性覆盖。"""

    eid: str
    name: str
    owner: str
    sin: Sin
    sp_cost: int
    corrosion_sp_cost: int
    awakening: Skill
    corrosion: Skill
    resist_override: dict = field(default_factory=dict)  # {Sin: float}
    passive_effects: list = field(default_factory=list)
    grade: str = ""
    description: str = ""
    source: str = ""
    confidence: str = "unverified"

    def variant(self, corrosion: bool = False) -> Skill:
        sk = self.corrosion if corrosion else self.awakening
        return sk

    def to_dict(self) -> dict:
        return {
            "eid": self.eid,
            "name": self.name,
            "owner": self.owner,
            "sin": self.sin.value,
            "sp_cost": self.sp_cost,
            "corrosion_sp_cost": self.corrosion_sp_cost,
            "awakening": self.awakening.to_dict(),
            "corrosion": self.corrosion.to_dict(),
            "resist_override": {(_k.value if isinstance(_k, Sin) else _k): v for _k, v in self.resist_override.items()},
            "passive_effects": self.passive_effects,
            "grade": self.grade,
            "description": self.description,
            "source": self.source,
            "confidence": self.confidence,
        }

    @staticmethod
    def from_dict(d: dict) -> "Ego":
        override = {}
        for k, v in (d.get("resist_override") or {}).items():
            if k.startswith("_"):
                override[k] = v
            else:
                override[Sin(k)] = float(v)
        return Ego(
            eid=d["eid"],
            name=d.get("name", d["eid"]),
            owner=d.get("owner", ""),
            sin=Sin(d.get("sin", "wrath")),
            sp_cost=int(d.get("sp_cost", 0)),
            corrosion_sp_cost=int(d.get("corrosion_sp_cost", d.get("sp_cost", 0))),
            awakening=Skill.from_dict(d["awakening"]),
            corrosion=Skill.from_dict(d.get("corrosion", d["awakening"])),
            resist_override=override,
            passive_effects=list(d.get("passive_effects", [])),
            grade=d.get("grade", ""),
            description=d.get("description", ""),
            source=d.get("source", ""),
            confidence=d.get("confidence", "unverified"),
        )
