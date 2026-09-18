"""单位状态：行动槽、状态效果、抗性、混乱阈值。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import DamageType, Side, Sin, SlotKind
from .skill import Ego, Skill
from .status import StatusRegistry, StatusStack


@dataclass
class ActionSlot:
    """一个行动槽。

    每回合：单位为每个槽抽到 2 个技能候选（``skill_choices``），
    规划阶段在 ``choice`` 里指定实际使用的技能 / E.G.O / 守备，
    并指定目标（``target_uid`` + ``target_slot``）。
    """

    index: int
    speed: int = 0
    skill_choices: list = field(default_factory=list)  # [sid, sid]（普通技能）
    choice_kind: SlotKind = SlotKind.SKILL
    choice_id: str = ""          # 技能 sid 或 E.G.O eid
    corrosion: bool = False      # E.G.O 是否使用侵蚀形态
    target_uid: str = ""
    target_slot: int = -1
    acted: bool = False          # 本回合是否已经结算
    cancelled: bool = False      # 被取消（混乱 / 死亡 / 目标消失）
    redirected: bool = False

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "speed": self.speed,
            "skill_choices": list(self.skill_choices),
            "choice_kind": self.choice_kind.value,
            "choice_id": self.choice_id,
            "corrosion": self.corrosion,
            "target_uid": self.target_uid,
            "target_slot": self.target_slot,
            "acted": self.acted,
            "cancelled": self.cancelled,
        }

    @staticmethod
    def from_dict(d: dict) -> "ActionSlot":
        s = ActionSlot(index=int(d["index"]))
        s.speed = int(d.get("speed", 0))
        s.skill_choices = list(d.get("skill_choices", []))
        s.choice_kind = SlotKind(d.get("choice_kind", "skill"))
        s.choice_id = d.get("choice_id", "")
        s.corrosion = bool(d.get("corrosion", False))
        s.target_uid = d.get("target_uid", "")
        s.target_slot = int(d.get("target_slot", -1))
        s.acted = bool(d.get("acted", False))
        s.cancelled = bool(d.get("cancelled", False))
        return s


@dataclass
class Unit:
    uid: str
    name: str
    side: Side
    max_hp: int
    hp: int = 0
    sp: int = 0
    max_sp: int = 45
    offense_level: int = 50
    defense_level: int = 50
    speed_range: tuple = (3, 7)
    stagger_thresholds: list = field(default_factory=list)  # 递减的 HP 阈值
    resistances: dict = field(default_factory=dict)         # DamageType -> 倍率
    sin_resistances: dict = field(default_factory=dict)     # Sin -> 倍率
    statuses: dict = field(default_factory=dict)
    slots: list = field(default_factory=list)
    identity: str = ""       # 人格 key（我方）
    ego_ids: list = field(default_factory=list)
    res: dict = field(default_factory=dict)   # 人格专属整数资源（弹药、生蝶、光札…）
    state: dict = field(default_factory=dict)  # 人格/Boss 专属杂项（形态、卡牌…）
    passive_effects: list = field(default_factory=list)
    kind: str = "identity"  # identity | boss | phantom
    time_type: str = ""     # 幻影所属时间类型
    tags: list = field(default_factory=list)
    alive: bool = True
    staggered: bool = False
    stagger_index: int = 0
    target_of_turn: bool = False  # 本回合是否被作为主要目标（幻影回补判定）
    ego_used_this_turn: bool = False
    resist_override: dict = field(default_factory=dict)
    guard: bool = False

    # ---------------------------------------------------------------- 基础
    def __post_init__(self) -> None:
        if self.hp <= 0:
            self.hp = self.max_hp
        if not self.resistances:
            self.resistances = {DamageType.SLASH: 1.0, DamageType.PIERCE: 1.0, DamageType.BLUNT: 1.0}
        if not self.sin_resistances:
            self.sin_resistances = {s: 1.0 for s in Sin}

    def hp_pct(self) -> float:
        return self.hp / self.max_hp if self.max_hp else 0.0

    # ---------------------------------------------------------------- 状态
    def status(self, key: str) -> StatusStack:
        st = self.statuses.get(key)
        if st is None:
            st = StatusStack(key)
            self.statuses[key] = st
        return st

    def status_potency(self, key: str) -> int:
        st = self.statuses.get(key)
        return st.potency if st else 0

    def status_count(self, key: str) -> int:
        st = self.statuses.get(key)
        return st.count if st else 0

    def has_status(self, key: str, min_potency: int = 1, min_count: int = 1) -> bool:
        st = self.statuses.get(key)
        if st is None:
            return False
        spec = status_spec(key)
        if spec.has_potency and st.potency < min_potency:
            return False
        if spec.has_count and st.count < min_count:
            return False
        if not spec.has_potency and not spec.has_count:
            return True
        return True

    def add_status(self, key: str, potency: int = 0, count: int = 0) -> None:
        st = self.status(key)
        st.potency = max(0, st.potency + potency)
        st.count = max(0, st.count + count)
        if st.is_empty() and key in self.statuses:
            # 保留空状态会更省事（避免 KeyError），但会污染 hash：直接删掉
            del self.statuses[key]

    def set_status(self, key: str, potency: int, count: int) -> None:
        if potency <= 0 and count <= 0:
            self.statuses.pop(key, None)
        else:
            st = self.status(key)
            st.potency = max(0, potency)
            st.count = max(0, count)

    def clear_status(self, key: str) -> None:
        self.statuses.pop(key, None)

    # ---------------------------------------------------------------- 攻防
    def effective_offense_level(self, bonus: int = 0) -> int:
        lvl = self.offense_level + bonus
        for key, st in self.statuses.items():
            spec = status_spec(key)
            if spec.offense_level_per_count:
                lvl += spec.offense_level_per_count * max(st.count, st.potency)
        return lvl

    def resistance(self, dtype: DamageType, sin: Sin) -> float:
        """物理抗性 × 罪孽抗性。

        E.G.O 使用后的罪孽抗性覆盖：``resist_override = {"_all_from_sin": "gloom"}``
        表示「本回合内所有罪孽伤害都按该 E.G.O 属性的抗性结算」。
        """
        base = self.resistances.get(dtype, 1.0)
        sr = self.sin_resistances.get(sin, 1.0)
        if self.resist_override:
            if "_all_from_sin" in self.resist_override:
                src = self.resist_override["_all_from_sin"]
                try:
                    src_sin = src if isinstance(src, Sin) else Sin(src)
                except ValueError:
                    src_sin = sin
                sr = self.sin_resistances.get(src_sin, 1.0)
            else:
                sr = self.resist_override.get(sin, sr)
        return base * sr

    def damage_taken_mult(self) -> float:
        mult = 1.0
        for key, st in self.statuses.items():
            spec = status_spec(key)
            if spec.damage_taken_mult_per_count:
                mult += spec.damage_taken_mult_per_count * st.count
            if spec.damage_taken_mult_per_potency:
                mult += spec.damage_taken_mult_per_potency * st.potency
        return mult

    def damage_dealt_mult(self) -> float:
        mult = 1.0
        for key, st in self.statuses.items():
            spec = status_spec(key)
            if spec.damage_dealt_mult_per_count:
                mult += spec.damage_dealt_mult_per_count * max(st.count, st.potency)
        return mult

    # ---------------------------------------------------------------- 序列化
    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "name": self.name,
            "side": self.side.value,
            "max_hp": self.max_hp,
            "hp": self.hp,
            "sp": self.sp,
            "offense_level": self.offense_level,
            "defense_level": self.defense_level,
            "stagger_thresholds": list(self.stagger_thresholds),
            "stagger_index": self.stagger_index,
            "staggered": self.staggered,
            "alive": self.alive,
            "identity": self.identity,
            "kind": self.kind,
            "time_type": self.time_type,
            "statuses": {k: v.to_dict() for k, v in sorted(self.statuses.items())},
            "res": {k: v for k, v in sorted(self.res.items())},
            "state": {k: v for k, v in sorted(self.state.items())},
            "slots": [s.to_dict() for s in self.slots],
            "resistances": {k.value: v for k, v in sorted(self.resistances.items(), key=lambda kv: kv[0].value)},
            "sin_resistances": {k.value: v for k, v in sorted(self.sin_resistances.items(), key=lambda kv: kv[0].value)},
            "resist_override": {_key_str(k): v for k, v in sorted(self.resist_override.items(), key=lambda kv: str(kv[0]))},
        }

    def copy(self) -> "Unit":
        u = Unit(
            uid=self.uid, name=self.name, side=self.side, max_hp=self.max_hp,
            hp=self.hp, sp=self.sp, max_sp=self.max_sp,
            offense_level=self.offense_level, defense_level=self.defense_level,
            speed_range=self.speed_range,
        )
        u.stagger_thresholds = list(self.stagger_thresholds)
        u.stagger_index = self.stagger_index
        u.staggered = self.staggered
        u.alive = self.alive
        u.resistances = dict(self.resistances)
        u.sin_resistances = dict(self.sin_resistances)
        u.statuses = {k: v.copy() for k, v in self.statuses.items()}
        u.slots = [ActionSlot.from_dict(s.to_dict()) for s in self.slots]
        u.identity = self.identity
        u.ego_ids = list(self.ego_ids)
        u.res = dict(self.res)
        u.state = {k: (list(v) if isinstance(v, list) else v) for k, v in self.state.items()}
        u.passive_effects = list(self.passive_effects)
        u.kind = self.kind
        u.time_type = self.time_type
        u.tags = list(self.tags)
        u.target_of_turn = self.target_of_turn
        u.ego_used_this_turn = self.ego_used_this_turn
        u.resist_override = dict(self.resist_override)
        u.guard = self.guard
        return u


# ---------------------------------------------------------------------------
# 全局状态注册表：引擎读数值倍率时需要 spec；由 content 层在加载数据后写入。
_STATUS_REGISTRY: StatusRegistry | None = None


def set_status_registry(reg: StatusRegistry) -> None:
    global _STATUS_REGISTRY
    _STATUS_REGISTRY = reg


def get_status_registry() -> StatusRegistry:
    global _STATUS_REGISTRY
    if _STATUS_REGISTRY is None:
        _STATUS_REGISTRY = StatusRegistry()
    return _STATUS_REGISTRY


def status_spec(key: str):
    return get_status_registry().get(key)


def _key_str(k) -> str:
    return k.value if isinstance(k, Sin) else str(k)
