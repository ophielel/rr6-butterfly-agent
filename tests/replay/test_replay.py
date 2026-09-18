"""Replay 往返与审计（计划书 §22）：录像必须能重跑、能定位分叉点。"""

from __future__ import annotations

import copy
import json
import unittest

from helpers import CONTENT
from rr6sim.core.config import SimConfig
from rr6sim.replay import export_replay, format_replay_text, replay_hash
from rr6sim.search.greedy import greedy_plan
from rr6sim.simulate import new_battle
from rr6sim.verify import event_digest, replay_turns, rerun_replay, verify_replay


def run_recorded(seed: int = 0, max_turns: int = 6):
    cfg = SimConfig(max_turns=max_turns, boss_hp_scale=0.25, boss_ai="script")
    battle = new_battle(CONTENT, cfg, seed=seed)
    while not battle.state.is_terminal() and battle.state.turn <= max_turns:
        plan = greedy_plan(battle)
        from rr6sim.simulate import apply_plan

        apply_plan(battle, plan)
        battle.resolve_turn()
        if battle.state.is_terminal():
            break
        battle.begin_turn()
    return battle


class TestReplayExport(unittest.TestCase):
    def setUp(self):
        self.battle = run_recorded()
        self.replay = export_replay(self.battle, run_id="test-run")

    def test_replay_contains_plans_per_turn(self):
        plans = replay_turns(self.replay)
        self.assertTrue(plans)
        self.assertTrue(all(entries for _, entries in plans))

    def test_json_roundtrip_keeps_hash(self):
        blob = json.dumps(self.replay, ensure_ascii=False)
        again = json.loads(blob)
        self.assertEqual(again["final_state_hash"], self.replay["final_state_hash"])
        self.assertEqual(replay_hash(again), replay_hash(self.replay))

    def test_text_format_runs(self):
        text = format_replay_text(self.replay)
        self.assertIn("outcome=", text)
        self.assertIn("Turn 1", text)


class TestReplayVerification(unittest.TestCase):
    def test_replay_reproduces_itself(self):
        replay = export_replay(run_recorded(seed=5))
        ok, report = verify_replay(CONTENT, replay)
        self.assertTrue(ok, report.get("first_divergence"))
        self.assertEqual(report["expected_hash"], report["actual_hash"])

    def test_tampered_plan_is_detected(self):
        replay = export_replay(run_recorded(seed=5))
        tampered = copy.deepcopy(replay)
        for block in tampered["turns"]:
            for e in block["events"]:
                if e.get("kind") == "plan" and e.get("entries"):
                    e["entries"][0]["target"] = "phantom_past"
                    e["entries"][0]["target_slot"] = 0
                    break
            else:
                continue
            break
        ok, report = verify_replay(CONTENT, tampered)
        self.assertFalse(ok)
        self.assertIsNotNone(report.get("first_divergence"))

    def test_rerun_matches_event_digest(self):
        battle = run_recorded(seed=3)
        replay = export_replay(battle)
        again = rerun_replay(CONTENT, replay)
        self.assertEqual(event_digest(again.state.log), event_digest(battle.state.log))

    def test_different_seed_diverges(self):
        replay = export_replay(run_recorded(seed=3))
        replay["seed"] = 999
        ok, _ = verify_replay(CONTENT, replay)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
