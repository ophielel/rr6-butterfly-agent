"""状态机层面的工具：构造战斗、执行完整回合计划、批量推进。

计划书 §11 要求 Rust 侧提供 ``clone_state / state_hash / legal_actions /
step_from_state / step_many / simulate_to_turn_end``。
这里给出等价实现（Python 版）。
"""

from __future__ import annotations

from typing import Iterable, Optional

from .core.config import SimConfig
from .core.engine import Battle
from .core.state import BattleState
from .core.status import FUTURE, PAST, PRESENT


def new_battle(content, config: Optional[SimConfig] = None, seed: int = 0,
               start_turn: bool = True) -> Battle:
    cfg = (config or SimConfig()).normalized()
    allies, enemies = content.make_encounter(cfg)
    st = BattleState(allies=allies, enemies=enemies, seed=seed, rng_state=seed, config=cfg)
    battle = Battle(st, content)
    if start_turn:
        battle.begin_turn()
    return battle


def apply_plan(battle: Battle, plan: Iterable[dict]) -> Battle:
    """把一条完整计划写进（尚未结算的）战斗。"""
    for entry in plan:
        owner = battle.unit(entry.get("owner", ""))
        if owner is None:
            raise KeyError(f"计划里的单位不存在: {entry}")
        slot = owner.slots[int(entry["slot"])]
        battle.assign_action(slot, entry["kind"], entry["id"], bool(entry.get("corrosion", False)))
        battle.assign_target(slot, entry.get("target", ""), int(entry.get("target_slot", -1)))
    return battle


def simulate_plan(content, state: BattleState, plan: Iterable[dict],
                  resolve: bool = True) -> Battle:
    """从给定 state 复制一份，写入计划并结算整回合。"""
    battle = Battle(state.copy(), content)
    battle.log_enabled = False
    apply_plan(battle, plan)
    if resolve:
        battle.resolve_turn()
    return battle


def simulate_to_turn_end(content, state: BattleState, plan: Iterable[dict]) -> BattleState:
    """:func:`simulate_plan` 的状态版（计划书 §11 的同名接口）。"""
    return simulate_plan(content, state, plan).state


def step_many(content, states: list, plans: list) -> list:
    """批量推进（未来可换成多进程/多线程；接口先固定下来）。"""
    out = []
    for st, plan in zip(states, plans):
        b = simulate_plan(content, st, plan)
        if not b.state.is_terminal():
            b.begin_turn()
        out.append(b.state)
    return out


def clone_state(state: BattleState) -> BattleState:
    return state.copy()


def state_hash(state: BattleState) -> str:
    return state.hash()


def stack_snapshot(state: BattleState) -> dict:
    boss = state.boss()
    if boss is None:
        return {}
    return {k: boss.status_count(k) for k in (PAST, PRESENT, FUTURE)}
