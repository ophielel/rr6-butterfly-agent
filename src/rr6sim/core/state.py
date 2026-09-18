"""战斗状态容器：可复制、可序列化、可 hash（计划书 §18.3）。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .config import SimConfig
from .enums import DamageType, Outcome, Phase, Side, Sin
from .unit import Unit


@dataclass
class BattleState:
    allies: list = field(default_factory=list)
    enemies: list = field(default_factory=list)
    turn: int = 0
    seed: int = 0
    rng_state: int = 0
    config: SimConfig = field(default_factory=SimConfig)
    plan: list = field(default_factory=list)
    phase: Phase = Phase.PLANNING
    log: list = field(default_factory=list)
    counters: dict = field(default_factory=dict)
    outcome: Outcome = Outcome.ONGOING
    terminal: dict = field(default_factory=dict)
    deck_cursor: dict = field(default_factory=dict)
    deck_queue: dict = field(default_factory=dict)
    script_pos: int = 0
    flags: dict = field(default_factory=dict)

    # ------------------------------------------------------------- 查询
    def units_of(self, side: Side) -> list:
        return self.allies if side is Side.ALLY else self.enemies

    def unit(self, uid: str):
        for u in self.allies:
            if u.uid == uid:
                return u
        for u in self.enemies:
            if u.uid == uid:
                return u
        return None

    def all_units(self) -> list:
        return list(self.allies) + list(self.enemies)

    def boss(self):
        for u in self.enemies:
            if u.kind == "boss":
                return u
        return None

    def phantoms(self) -> list:
        return [u for u in self.enemies if u.kind == "phantom"]

    def alive_allies(self) -> list:
        return [u for u in self.allies if u.alive]

    def alive_enemies(self) -> list:
        return [u for u in self.enemies if u.alive]

    def is_terminal(self) -> bool:
        return self.phase is Phase.TERMINAL

    # ------------------------------------------------------------- 序列化
    def to_dict(self, include_log: bool = True) -> dict:
        d = {
            "turn": self.turn,
            "seed": self.seed,
            "rng_state": self.rng_state,
            "config": self.config.to_dict(),
            "config_hash": self.config.hash(),
            "allies": [u.to_dict() for u in self.allies],
            "enemies": [u.to_dict() for u in self.enemies],
            "plan": list(self.plan),
            "phase": self.phase.value,
            "counters": dict(self.counters),
            "outcome": self.outcome.value,
            "terminal": dict(self.terminal),
            "flags": dict(self.flags),
            "script_pos": self.script_pos,
            # 技能牌堆是隐藏信息，但**会影响未来状态转移**，必须进 transition hash
            "deck_queue": {k: list(v) for k, v in sorted(self.deck_queue.items())},
            "deck_cursor": dict(sorted(self.deck_cursor.items())),
        }
        if include_log:
            d["log"] = list(self.log)
        return d

    def canonical(self, hidden: bool = True) -> str:
        """用于 hash 的规范字符串（不含 log）。

        ``hidden=True`` 时包含一切会影响**未来状态转移**的信息：
        RNG 状态、技能牌堆、Boss 隐藏状态、flags、counters…
        ``hidden=False`` 时只保留玩家可见的局面（用于训练/诊断）。
        """
        d = self.to_dict(include_log=False)
        if not hidden:
            for key in ("rng_state", "deck_queue", "deck_cursor", "script_pos",
                        "seed", "flags", "counters", "terminal"):
                d.pop(key, None)
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    # ------------------------------------------------------------- hash
    def transition_hash(self, include_counters: bool = True) -> str:
        """状态转移 hash：Beam / MCTS / 置换表必须用这个。

        包含 rng_state、技能牌堆（deck_queue / deck_cursor）、flags（深）、
        Boss 隐藏状态、counters。**同局面不同 RNG 必须得到不同 hash。**
        """
        d = self.to_dict(include_log=False)
        if not include_counters:
            d.pop("counters", None)
        blob = json.dumps(d, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]

    def observation_hash(self) -> str:
        """观察 hash：只含玩家可见信息，用于训练诊断 / 去重可视化。"""
        return hashlib.sha1(self.canonical(hidden=False).encode("utf-8")).hexdigest()[:16]

    def hash(self) -> str:
        """默认即 transition hash（计划书 / 搜索接口的 ``state_hash()``）。"""
        return self.transition_hash()

    def copy(self) -> "BattleState":
        from .unit import _deep

        st = BattleState(
            allies=[u.copy() for u in self.allies],
            enemies=[u.copy() for u in self.enemies],
            turn=self.turn,
            seed=self.seed,
            rng_state=self.rng_state,
            config=self.config,
            plan=_deep(self.plan),
            phase=self.phase,
            log=_deep(self.log),
            counters=dict(self.counters),
            outcome=self.outcome,
            terminal=_deep(self.terminal),
            deck_cursor=dict(self.deck_cursor),
            deck_queue={k: list(v) for k, v in self.deck_queue.items()},
            script_pos=self.script_pos,
            flags=_deep(self.flags),
        )
        return st


def _deser_unit(d: dict) -> Unit:
    u = Unit(uid=d["uid"], name=d["name"], side=Side(d["side"]), max_hp=int(d["max_hp"]))
    u.hp = int(d["hp"])
    u.sp = int(d["sp"])
    u.offense_level = int(d.get("offense_level", 50))
    u.defense_level = int(d.get("defense_level", 50))
    u.stagger_thresholds = list(d.get("stagger_thresholds", []))
    u.stagger_index = int(d.get("stagger_index", 0))
    u.staggered = bool(d.get("staggered", False))
    u.alive = bool(d.get("alive", True))
    u.shield = int(d.get("shield", 0))
    u.identity = d.get("identity", "")
    u.kind = d.get("kind", "identity")
    u.time_type = d.get("time_type", "")
    u.targetable = bool(d.get("targetable", True))
    u.has_sanity = bool(d.get("has_sanity", True))
    u.stagger_level = int(d.get("stagger_level", 0))
    u.resistances = {DamageType(k): float(v) for k, v in (d.get("resistances") or {}).items()}
    u.sin_resistances = {Sin(k): float(v) for k, v in (d.get("sin_resistances") or {}).items()}
    from .status import StatusStack

    u.statuses = {k: StatusStack.from_dict(v) for k, v in (d.get("statuses") or {}).items()}
    u.res = {k: int(v) for k, v in (d.get("res") or {}).items()}
    u.state = dict(d.get("state") or {})
    from .unit import ActionSlot

    u.slots = [ActionSlot.from_dict(s) for s in (d.get("slots") or [])]
    u.resist_override = {}
    for k, v in (d.get("resist_override") or {}).items():
        key = k if k.startswith("_") else Sin(k)
        u.resist_override[key] = float(v) if not isinstance(v, str) else v
    return u


def state_from_dict(d: dict) -> BattleState:
    st = BattleState(
        allies=[_deser_unit(x) for x in d.get("allies", [])],
        enemies=[_deser_unit(x) for x in d.get("enemies", [])],
        turn=int(d.get("turn", 0)),
        seed=int(d.get("seed", 0)),
        rng_state=int(d.get("rng_state", 0)),
        config=SimConfig.from_dict(d.get("config") or {}),
        plan=list(d.get("plan") or []),
        phase=Phase(d.get("phase", "planning")),
        counters=dict(d.get("counters") or {}),
        outcome=Outcome(d.get("outcome", "ongoing")),
        terminal=dict(d.get("terminal") or {}),
        flags=dict(d.get("flags") or {}),
        script_pos=int(d.get("script_pos", 0)),
    )
    st.deck_queue = {k: list(v) for k, v in (d.get("deck_queue") or {}).items()}
    st.deck_cursor = dict(d.get("deck_cursor") or {})
    st.log = list(d.get("log") or [])
    return st
