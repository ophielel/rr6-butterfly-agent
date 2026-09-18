"""测试辅助：极小型战斗（1~2 个单位 + 自定义技能），方便手算断言。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from rr6sim.content import Content  # noqa: E402
from rr6sim.core.config import SimConfig  # noqa: E402
from rr6sim.core.engine import Battle  # noqa: E402
from rr6sim.core.enums import DamageType, Side, Sin, TargetMode  # noqa: E402
from rr6sim.core.skill import Skill  # noqa: E402
from rr6sim.core.state import BattleState  # noqa: E402
from rr6sim.core.unit import ActionSlot, Unit  # noqa: E402

#: 共享一份内容（数据加载只做一次；状态注册表是全局的）
CONTENT = Content()


def register(sk: Skill) -> Skill:
    CONTENT.skills[sk.sid] = sk
    return sk


def make_skill(sid: str, *, coins=3, power=0, damage=10, coin_kind="positive",
               sin="wrath", damage_type="slash", base_power=5,
               coin_effects=None, effects=None, **kw) -> Skill:
    d = {
        "sid": sid,
        "name": sid,
        "sin": sin,
        "damage_type": damage_type,
        "base_power": base_power,
        "coins": [{"kind": coin_kind, "power": power, "damage": damage,
                   "effects": list(coin_effects or [])} for _ in range(coins)],
        "effects": list(effects or []),
    }
    d.update(kw)
    return register(Skill.from_dict(d))


def make_unit(uid: str, side: Side = Side.ALLY, hp: int = 100, *, sp: int = 0,
              offense: int = 50, defense: int = 50, slots: int = 1, kind: str = "identity",
              speed: int = 5, **kw) -> Unit:
    u = Unit(uid=uid, name=uid, side=side, max_hp=hp, hp=hp, sp=sp,
             offense_level=offense, defense_level=defense,
             speed_range=(speed, speed), max_sp=45)
    u.kind = kind
    u.slots = [ActionSlot(index=i) for i in range(slots)]
    for s in u.slots:
        s.speed = speed
    for key, value in kw.items():
        setattr(u, key, value)
    return u


def make_battle(allies: list, enemies: list, config: SimConfig = None, seed: int = 0,
                log: bool = False) -> Battle:
    cfg = (config or SimConfig()).normalized() if config is not None else SimConfig(coin_mode="always_heads").normalized()
    st = BattleState(allies=list(allies), enemies=list(enemies), config=cfg, seed=seed, rng_state=seed)
    b = Battle(st, CONTENT)
    b.log_enabled = log
    return b


def attack(battle: Battle, actor: Unit, target: Unit, skill, slot_index: int = 0,
           mode: TargetMode = TargetMode.ONE_SIDED) -> None:
    """直接执行一次攻击（跳过速度/计划）。"""
    sk = CONTENT.skill(skill) if isinstance(skill, str) else skill
    battle.execute_attack(actor, actor.slots[slot_index], sk, target, mode)


def all_heads(**kw) -> SimConfig:
    kw.setdefault("coin_mode", "always_heads")
    return SimConfig(**kw)


def attack_with(self, actor: Unit, skill, target: Unit, slot_index: int = 0) -> None:
    """直接攻击（测试辅助，绑定到 Battle）。"""
    sk = CONTENT.skill(skill) if isinstance(skill, str) else skill
    actor.state["_clash_bonus"] = 0
    self.execute_attack(actor, actor.slots[slot_index], sk, target,
                        __import__("rr6sim.core.enums", fromlist=["TargetMode"]).TargetMode.ONE_SIDED)


Battle.attack_with = attack_with


def coin_log(battle: Battle) -> list:
    return [e for e in battle.state.log if e.get("kind") == "coin"]
