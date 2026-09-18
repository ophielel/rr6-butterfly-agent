"""replay 验证器（计划书 §18.2 / §18.3 / §22）。

出现「AI 找到 2T 神轴」时，第一件事不是庆祝，而是把 replay 丢进这里逐事件审计：

* 用记录的每回合计划 + 同一个 seed 重跑一遍；
* 比对最终 state hash；
* 比对事件摘要（硬币正反、伤害量、状态变化、形态切换…）。

只要模拟器结算错一条「命中时」或「攻击后」，重跑就会和录像分叉。
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional, Tuple

from .core.engine import Battle
from .core.config import SimConfig
from .core.state import BattleState
from .content.loader import Content
from .simulate import apply_plan


#: 参与摘要比对的事件字段（顺序固定，保证 hash 稳定）
DIGEST_KINDS = ("plan", "clash_roll", "coin", "damage", "status", "sp", "stacks",
                "form_change", "stagger", "death", "ego_use", "transfer",
                "phantom_broken", "phantom_revive", "hp_threshold", "terminal",
                "turn_hash")


def event_digest(log: list) -> str:
    rows = []
    for e in log:
        kind = e.get("kind")
        if kind not in DIGEST_KINDS:
            continue
        rows.append(json.dumps({k: e.get(k) for k in sorted(e)}, sort_keys=True, ensure_ascii=False))
    return hashlib.sha1("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def replay_turns(replay: dict) -> list:
    """从 replay 里取出每回合的计划列表。"""
    plans = []
    for block in replay.get("turns", []):
        entries = []
        for e in block.get("events", []):
            if e.get("kind") == "plan":
                entries = list(e.get("entries") or [])
                break
        plans.append((block.get("turn"), entries))
    return plans


def rerun_replay(content: Content, replay: dict, log: bool = True) -> Battle:
    cfg = SimConfig.from_dict(replay.get("config") or {}).normalized()
    seed = int(replay.get("seed", 0))
    allies, enemies = content.make_encounter(cfg)
    st = BattleState(allies=allies, enemies=enemies, seed=seed, rng_state=seed, config=cfg)
    battle = Battle(st, content)
    battle.log_enabled = log
    battle.begin_turn()
    for _turn, entries in replay_turns(replay):
        if battle.state.is_terminal():
            break
        apply_plan(battle, entries)
        battle.resolve_turn()
        if battle.state.is_terminal():
            break
        battle.begin_turn()
    return battle


def verify_replay(content: Content, replay: dict) -> Tuple[bool, dict]:
    """重跑并比对。返回 ``(是否一致, 报告)``。"""
    battle = rerun_replay(content, replay, log=True)
    report = {
        "expected_hash": replay.get("final_state_hash"),
        "actual_hash": battle.state.hash(),
        "expected_outcome": replay.get("outcome"),
        "actual_outcome": battle.state.outcome.value,
        "expected_digest": event_digest(_flatten(replay)),
        "actual_digest": event_digest(battle.state.log),
        "expected_counters": replay.get("counters") or {},
        "actual_counters": dict(battle.state.counters),
    }
    ok = (report["expected_hash"] == report["actual_hash"]
          and report["expected_outcome"] == report["actual_outcome"]
          and report["expected_digest"] == report["actual_digest"])
    report["match"] = ok
    if not ok:
        report["first_divergence"] = _first_divergence(_flatten(replay), battle.state.log)
    return ok, report


def _flatten(replay: dict) -> list:
    out = []
    for block in replay.get("turns", []):
        out.extend(block.get("events", []))
    return out


def _first_divergence(recorded: list, actual: list) -> Optional[dict]:
    ra = [e for e in recorded if e.get("kind") in DIGEST_KINDS]
    rb = [e for e in actual if e.get("kind") in DIGEST_KINDS]
    for i in range(max(len(ra), len(rb))):
        a = ra[i] if i < len(ra) else None
        b = rb[i] if i < len(rb) else None
        if a != b:
            return {"index": i, "recorded": a, "replayed": b}
    return None
