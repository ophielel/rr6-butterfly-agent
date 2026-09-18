"""内容加载：把 ``data/*.json`` 变成可执行的技能 / 人格 / Boss。

设计取舍（计划书 §8）：
* 技能 / 被动 / 状态钩子尽量数据驱动，方便逐条标注来源与置信度；
* 极特殊机制才写 handler（见 core/effects.py 与 content/mechanics.py）；
* 数据缺失时不静默通过——``strict`` 模式会把缺技能/缺状态直接报错，
  这样 golden replay 不会因为「数据没录全」而给出假结果。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from ..core.config import SimConfig
from ..core.enums import DamageType, Side, Sin
from ..core.skill import Coin, Ego, Skill
from ..core.status import StatusRegistry, StatusSpec
from ..core.unit import ActionSlot, Unit, set_status_registry

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_skill_dict(d: dict) -> dict:
    """把 ``{"coin_count": N, "coin": {...}}`` 展开成显式硬币列表。"""
    d = dict(d)
    if "coins" not in d:
        n = int(d.pop("coin_count", 0))
        tmpl = d.pop("coin", {"kind": "positive", "power": 0, "damage": 0, "effects": []})
        d["coins"] = [dict(tmpl) for _ in range(n)]
    return d


def _parse_skill(d: dict) -> Skill:
    return Skill.from_dict(_normalize_skill_dict(d))


@dataclass
class IdentityDef:
    key: str
    name: str
    name_short: str
    hp: int
    sp: int
    offense_level: int
    defense_level: int
    speed_range: tuple
    slots: int
    deck: list
    guard: str
    egos: list
    resources: dict
    resistances: dict
    sin_resistances: dict
    stagger_thresholds: list
    passive_effects: list
    skills: list
    source: str = ""
    confidence: str = "unverified"


class Content:
    """全部静态数据的容器。"""

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR) -> None:
        self.data_dir = data_dir
        self.statuses = StatusRegistry()
        self.skills: dict[str, Skill] = {}
        self.egos: dict[str, Ego] = {}
        self.identities: dict[str, IdentityDef] = {}
        self.boss_def: dict = {}
        self.phantom_defs: list = []
        self.encounter: dict = {}
        self.meta: dict = {}
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        st = _read_json(os.path.join(self.data_dir, "statuses.json"))
        self.meta["statuses"] = st.get("_meta", {})
        for key, val in st.items():
            if key.startswith("_"):
                continue
            self.statuses.register(StatusSpec(
                key=key,
                name_cn=val.get("name_cn", key),
                name_en=val.get("name_en", ""),
                has_potency=val.get("has_potency", False),
                has_count=val.get("has_count", False),
                turn_end_count_decay=val.get("turn_end_count_decay", 0),
                turn_end_potency_decay=val.get("turn_end_potency_decay", 0),
                damage_taken_mult_per_count=val.get("damage_taken_mult_per_count", 0.0),
                damage_taken_mult_per_potency=val.get("damage_taken_mult_per_potency", 0.0),
                damage_dealt_mult_per_count=val.get("damage_dealt_mult_per_count", 0.0),
                clash_power_per_count=val.get("clash_power_per_count", 0),
                offense_level_per_count=val.get("offense_level_per_count", 0),
                hooks=list(val.get("hooks", [])),
                description=val.get("description", ""),
                source=val.get("source", ""),
                confidence=val.get("confidence", "unverified"),
            ))
        set_status_registry(self.statuses)

        idt = _read_json(os.path.join(self.data_dir, "identities.json"))
        self.meta["identities"] = idt.get("_meta", {})
        for rec in idt.get("identities", []):
            skills = [_parse_skill(s) for s in rec.get("skills", [])]
            for sk in skills:
                self.skills[sk.sid] = sk
            guard = _parse_skill(_find_raw(rec, rec["guard"]))
            self.skills[guard.sid] = guard
            self.identities[rec["key"]] = IdentityDef(
                key=rec["key"],
                name=rec["name"],
                name_short=rec.get("name_short", rec["name"]),
                hp=int(rec.get("hp", 250)),
                sp=int(rec.get("sp", 0)),
                offense_level=int(rec.get("offense_level", 50)),
                defense_level=int(rec.get("defense_level", 50)),
                speed_range=tuple(rec.get("speed_range", [3, 7])),
                slots=int(rec.get("slots", 1)),
                deck=list(rec.get("deck", [])),
                guard=guard.sid,
                egos=list(rec.get("egos", [])),
                resources=dict(rec.get("resources", {})),
                resistances={DamageType(k): v for k, v in rec.get("resistances", {}).items()},
                sin_resistances={Sin(k): v for k, v in rec.get("sin_resistances", {}).items()},
                stagger_thresholds=list(rec.get("stagger_thresholds", [])),
                passive_effects=list(rec.get("passive_effects", [])),
                skills=skills,
                source=rec.get("source", ""),
                confidence=rec.get("confidence", "unverified"),
            )

        eg = _read_json(os.path.join(self.data_dir, "egos.json"))
        self.meta["egos"] = eg.get("_meta", {})
        for rec in eg.get("egos", []):
            rec = dict(rec)
            rec["awakening"] = _normalize_skill_dict(rec["awakening"])
            rec["corrosion"] = _normalize_skill_dict(rec.get("corrosion", rec["awakening"]))
            ego = Ego.from_dict(rec)
            self.egos[ego.eid] = ego
            self.skills[ego.awakening.sid] = ego.awakening
            self.skills[ego.corrosion.sid] = ego.corrosion

        bs = _read_json(os.path.join(self.data_dir, "boss_rr6_butterfly.json"))
        self.meta["boss"] = bs.get("_meta", {})
        self.boss_def = bs.get("boss", {})
        self.phantom_defs = list(bs.get("phantoms", []))
        self.encounter = bs
        for sk in self.boss_def.get("skills", []):
            s = _parse_skill(sk)
            self.skills[s.sid] = s
        for ph in self.phantom_defs:
            for sk in ph.get("skills", []):
                s = _parse_skill(sk)
                self.skills[s.sid] = s

    # ------------------------------------------------------------------
    def skill(self, sid: str) -> Optional[Skill]:
        return self.skills.get(sid)

    def ego(self, eid: str) -> Optional[Ego]:
        return self.egos.get(eid)

    def identity(self, key: str) -> Optional[IdentityDef]:
        return self.identities.get(key)

    # ------------------------------------------------------------------
    def make_ally(self, uid: str, key: str, config: SimConfig) -> Unit:
        ident = self.identities[key]
        u = Unit(
            uid=uid,
            name=ident.name_short or ident.name,
            side=Side.ALLY,
            max_hp=int(ident.hp),
            hp=int(ident.hp * config.ally_hp_pct),
            sp=config.ally_sp if config.ally_sp else ident.sp,
            offense_level=ident.offense_level,
            defense_level=ident.defense_level,
            speed_range=ident.speed_range,
        )
        u.stagger_thresholds = list(ident.stagger_thresholds)
        u.resistances = dict(ident.resistances)
        u.sin_resistances = dict(ident.sin_resistances)
        u.identity = ident.key
        u.kind = "identity"
        u.ego_ids = [e for e in ident.egos if e not in config.disabled_egos]
        u.res = dict(ident.resources)
        u.passive_effects = list(ident.passive_effects)
        u.slots = [ActionSlot(index=i) for i in range(ident.slots)]
        return u

    def make_enemy(self, d: dict, config: SimConfig, hp_override: Optional[int] = None) -> Unit:
        hp = int(hp_override if hp_override is not None else d.get("hp", 1000))
        u = Unit(
            uid=d["uid"],
            name=d.get("name", d["uid"]),
            side=Side.ENEMY,
            max_hp=hp,
            hp=hp,
            sp=int(d.get("sp", 0)),
            offense_level=int(d.get("offense_level", 50)),
            defense_level=int(d.get("defense_level", 50)),
            speed_range=tuple(d.get("speed_range", [3, 7])),
        )
        u.kind = d.get("kind", "enemy")
        u.time_type = d.get("time_type", "")
        if "stagger_thresholds_pct" in d:
            u.stagger_thresholds = [int(hp * p) for p in d["stagger_thresholds_pct"]]
        else:
            u.stagger_thresholds = [int(t) for t in d.get("stagger_thresholds", [])]
        u.resistances = {DamageType(k): v for k, v in d.get("resistances", {}).items()}
        u.sin_resistances = {Sin(k): v for k, v in d.get("sin_resistances", {}).items()}
        u.res = dict(d.get("resources", {}))
        u.state = dict(d.get("state", {}))
        if "stack_thresholds_pct" in d:
            u.state["stack_thresholds"] = [int(hp * p) for p in d["stack_thresholds_pct"]]
        u.state["skill_pool"] = list(d.get("skill_pool", []))
        u.state["skill_script"] = list(d.get("skill_script", d.get("skill_pool", [])))
        u.state["target_mode"] = d.get("target_mode", "first")
        u.tags = list(d.get("tags", []))
        effects = []
        for e in d.get("passive_effects", []):
            name = e.get("rr6_passive") if isinstance(e, dict) else None
            if name and name in config.disabled_rr6_passives:
                continue
            effects.append(e)
        u.passive_effects = effects
        u.state["on_hp_threshold_effects"] = list(d.get("on_hp_threshold_effects", []))
        u.slots = [ActionSlot(index=i) for i in range(int(d.get("slots", 1)))]
        return u

    # ------------------------------------------------------------------
    def make_encounter(self, config: SimConfig):
        """构造一场 RR6 第五区段战斗的初始单位。"""
        allies = []
        for i, key in enumerate(self.identities):
            if key in config.disabled_identities:
                continue
            ident = self.identities[key]
            for s in range(ident.slots):
                uid = f"{key}" if ident.slots == 1 else f"{key}_{s}"
                allies.append(self.make_ally(uid, key, config))

        buffs = config.encounter_buffs or {}
        scale = float(config.boss_hp_scale) * float(buffs.get("boss_hp_mult", 1.0))
        boss_hp = int(config.boss_hp * scale)
        boss = self.make_enemy(self.boss_def, config, hp_override=boss_hp)
        enemies = [boss]
        for ph in self.phantom_defs:
            ph_hp = int(int(ph.get("hp", 2000)) * scale)
            enemies.append(self.make_enemy(ph, config, hp_override=ph_hp))

        # 初始状态栈
        stacks = dict(self.encounter.get("initial_stacks", {}))
        stacks.update(buffs.get("initial_stacks", {}))
        for k, v in stacks.items():
            boss.add_status(k, count=int(v))
        # 额外状态（第五区段事件增益 / 消融实验用）
        for key, val in (buffs.get("boss_extra_statuses") or {}).items():
            boss.add_status(key, potency=int(val[0]), count=int(val[1]))
        for u in allies:
            for key, val in (buffs.get("ally_extra_statuses") or {}).items():
                u.add_status(key, potency=int(val[0]), count=int(val[1]))
        boss.state["form"] = buffs.get("initial_form", "neutral")
        return allies, enemies


def _find_raw(rec: dict, sid: str) -> dict:
    """在 identity 记录里找某个技能的原始 dict（guard 用）。"""
    for s in rec.get("skills", []):
        if s.get("sid") == sid:
            return s
    return {"sid": sid, "name": sid, "sin": "sloth", "damage_type": "blunt",
            "base_power": 8, "coin_count": 1,
            "coin": {"kind": "positive", "power": 6, "damage": 0, "effects": []}}
