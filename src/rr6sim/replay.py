"""replay 导出（计划书 §22）。

每次实验都保存纯文本 / JSON replay，出现「AI 找到神轴」时第一件事是
把它丢进验证器逐事件审计，而不是庆祝。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Optional

from .core.status import FUTURE, PAST, PRESENT, TIMEGAP


def export_replay(battle, run_id: Optional[str] = None, config_hash: Optional[str] = None) -> dict:
    st = battle.state
    boss = st.boss()
    rep = {
        "run_id": run_id or f"run-{int(time.time())}-{st.seed}",
        "code_version": "rr6sim-0.1",
        "data_version": battle.content.meta.get("boss", {}).get(
            "game_version", battle.content.meta.get("statuses", {}).get("game_version", "unknown")),
        "data_confidence": {
            "statuses": battle.content.meta.get("statuses", {}).get("wiki_accessible", True),
            "boss": (battle.content.meta.get("boss", {}) or {}).get("confidence", "unknown"),
        },
        "config": st.config.to_dict(),
        "config_hash": config_hash or st.config.hash(),
        "seed": st.seed,
        "initial_state": {
            "allies": [{"uid": u.uid, "identity": u.identity, "hp": u.hp, "sp": u.sp}
                       for u in st.allies],
            "enemies": [{"uid": u.uid, "kind": u.kind, "hp": u.hp} for u in st.enemies],
        },
        "turns": _group_turns(st.log),
        "turn_hashes": [b["end_state_hash"] for b in _group_turns(st.log)],
        "terminal": dict(st.terminal),
        "outcome": st.outcome.value,
        "counters": dict(st.counters),
        "boss_final": {
            "hp": boss.hp if boss else 0,
            "sp": boss.sp if boss else 0,
            "form": boss.state.get("form") if boss else "",
            "stacks": {k: boss.status_count(k) for k in (PAST, PRESENT, FUTURE)} if boss else {},
            "timegap": boss.status_count(TIMEGAP) if boss else 0,
        },
        "stats": {
            "kill_turn": st.terminal.get("kill_turn"),
            "total_damage": st.counters.get("total_damage", 0),
            "ego_usage": st.counters.get("ego_use", 0),
            "repeat_coin_count": st.counters.get("repeat_coin", 0),
            "sinking_sp_damage": st.counters.get("sinking_sp_damage", 0),
            "butterfly_hp_damage": st.counters.get("butterfly_hp_damage", 0),
            "phantom_stack_decay": st.counters.get("phantom_stack_decay", 0),
            "form_switch": st.counters.get("form_switch", 0),
            "clash_count": st.counters.get("clash_count", 0),
            "stagger_count": st.counters.get("stagger_count", 0),
        },
        "final_state_hash": st.hash(),
    }
    return rep


def _group_turns(log: list) -> list:
    turns: dict = {}
    for entry in log:
        turns.setdefault(entry.get("turn", 0), []).append(entry)
    out = []
    for t in sorted(turns):
        events = turns[t]
        end_hash = ""
        for e in events:
            if e.get("kind") == "turn_hash":
                end_hash = e.get("hash", "")
        out.append({"turn": t, "end_state_hash": end_hash, "events": events})
    return out


def save_replay(replay: dict, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(replay, f, ensure_ascii=False, indent=1)
    return path


def replay_hash(replay: dict) -> str:
    blob = json.dumps(replay.get("turns", []), sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def format_replay_text(replay: dict, max_events: int = 0) -> str:
    """人类可读的 replay 摘要（用于 golden replay 对比）。"""
    lines = [
        f"run_id={replay['run_id']} seed={replay['seed']} config_hash={replay['config_hash']}",
        f"outcome={replay['outcome']} terminal={replay['terminal']}",
        f"stats={replay['stats']}",
    ]
    for t in replay["turns"]:
        lines.append(f"--- Turn {t['turn']} ---")
        evs = t["events"]
        if max_events:
            evs = evs[:max_events]
        for e in evs:
            kind = e.get("kind")
            if kind == "coin":
                lines.append(f"  coin {e['unit']}->{e['target']} {e['skill']}#{e['coin']} "
                             f"{'表' if e['heads'] else '里'} power={e['power']} dmg={e['damage']}")
            elif kind == "damage":
                lines.append(f"  dmg {e['source']}->{e['target']} {e['amount']} "
                             f"({e['origin']}) hp={e['hp']}")
            elif kind == "status":
                lines.append(f"  status {e['unit']} {e['status']} +{e['potency']}/+{e['count']} "
                             f"=> {e['total_potency']}/{e['total_count']}")
            elif kind == "sp":
                lines.append(f"  sp {e['unit']} {e['before']}->{e['after']} ({e['source']})")
            elif kind == "stacks":
                lines.append(f"  stacks {e['amount']:+d} [{e['time']}] {e['reason']} -> {e['boss']}")
            elif kind == "form_change":
                lines.append(f"  form {e['from']} -> {e['to']} {e['stacks']}")
            elif kind == "clash_roll":
                lines.append(f"  clash a={e['a_power']}({e['a_heads']}) vs b={e['b_power']}({e['b_heads']}) {e['result']}")
            elif kind == "ego_use":
                lines.append(f"  ego {e['unit']} {e['ego']} corrosion={e['corrosion']} sp {e['sp_before']}->{e['sp_after']}")
            elif kind == "stagger":
                lines.append(f"  stagger {e['unit']}")
            elif kind == "terminal":
                lines.append(f"  terminal {e}")
    return "\n".join(lines)
