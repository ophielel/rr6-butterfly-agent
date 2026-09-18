"""状态复制 / hash / 确定性 / 环境接口验证（计划书 §11 / §18.3）。"""

from __future__ import annotations

import unittest

from helpers import CONTENT, all_heads, attack, make_battle, make_skill, make_unit
from rr6sim import RR6ButterflyEnv, SimConfig
from rr6sim.core.enums import Side
from rr6sim.search.greedy import greedy_plan
from rr6sim.simulate import new_battle, simulate_plan


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_result(self):
        from rr6sim.search.greedy import run_greedy

        cfg = SimConfig(max_turns=12, boss_hp_scale=0.25)
        a = run_greedy(CONTENT, cfg, seed=3)
        b = run_greedy(CONTENT, cfg, seed=3)
        self.assertEqual(a["turns"], b["turns"])
        self.assertEqual(a["boss_hp"], b["boss_hp"])
        self.assertEqual(a["battle"].state.hash(), b["battle"].state.hash())

    def test_coin_script_is_deterministic(self):
        sk = make_skill("t_dt1", coins=1, power=10, damage=10)
        a = make_unit("a", Side.ALLY)
        for expected_heads, expected_damage in ((True, 20), (False, 10)):
            e = make_unit("e", Side.ENEMY, hp=999)
            cfg = SimConfig(coin_mode="script", coin_script=[expected_heads])
            b = make_battle([a], [e], cfg)
            attack(b, a, e, sk)
            self.assertEqual(e.hp, 999 - expected_damage)

    def test_clone_isolated_from_original(self):
        b = new_battle(CONTENT, SimConfig(boss_hp_scale=0.25), seed=1)
        clone = b.clone()
        boss = clone.boss()
        boss.hp -= 5000
        self.assertNotEqual(clone.state.hash(), b.state.hash())
        self.assertNotEqual(clone.boss().hp, b.boss().hp)

    def test_simulate_plan_does_not_mutate_source(self):
        b = new_battle(CONTENT, SimConfig(boss_hp_scale=0.25), seed=1)
        before = b.state.hash()
        plan = greedy_plan(b)
        simulate_plan(CONTENT, b.state, plan)
        self.assertEqual(b.state.hash(), before)

    def test_state_serialization_roundtrip(self):
        from rr6sim.core.state import state_from_dict

        b = new_battle(CONTENT, SimConfig(boss_hp_scale=0.25), seed=1)
        plan = greedy_plan(b)
        simulate_plan(CONTENT, b.state, plan)
        d = b.state.to_dict()
        again = state_from_dict(d)
        self.assertEqual(again.hash(), b.state.hash())


class TestEnvironment(unittest.TestCase):
    def setUp(self):
        self.env = RR6ButterflyEnv(SimConfig(max_turns=6, boss_hp_scale=0.25), seed=2)
        self.env.reset(seed=2)

    def test_observation_shape_stable(self):
        size = self.env.observation_size
        names = self.env.observation_names()
        self.assertEqual(size, len(names))
        env = RR6ButterflyEnv(SimConfig(max_turns=6, boss_hp_scale=0.25), seed=9)
        env.reset(seed=9)
        self.assertEqual(env.observation_size, size)

    def test_autoregressive_plan_then_resolve(self):
        turns_seen = {self.env.battle.state.turn}
        for _ in range(200):
            legal = self.env.legal_actions()
            if not legal:
                break
            obs, reward, term, trunc, info = self.env.step(0)
            if term or trunc:
                break
            turns_seen.add(info.get("turn"))
        self.assertGreaterEqual(len(turns_seen), 2)

    def test_illegal_action_index_is_reported(self):
        obs, reward, term, trunc, info = self.env.step(10 ** 6)
        self.assertTrue(info["invalid"])

    def test_legal_action_mask_matches(self):
        mask = self.env.legal_action_mask()
        self.assertEqual(len(mask), len(self.env.legal_actions()))
        self.assertTrue(all(mask))

    def test_full_turn_via_step_plan(self):
        plan = greedy_plan(self.env.battle)
        obs, reward, term, trunc, info = self.env.step_plan(plan)
        self.assertEqual(info["turn"], 2)
        self.assertEqual(reward, self.env.config.reward_turn_penalty)

    def test_kill_gives_positive_reward(self):
        env = RR6ButterflyEnv(SimConfig(max_turns=40, boss_hp_scale=0.05), seed=0)
        env.reset(seed=0)
        reward = 0.0
        for _ in range(60):
            plan = greedy_plan(env.battle)
            obs, r, term, trunc, info = env.step_plan(plan)
            reward += r
            if term or trunc:
                break
        self.assertTrue(term)
        self.assertGreater(reward, 0)

    def test_export_replay_has_expected_fields(self):
        plan = greedy_plan(self.env.battle)
        self.env.step_plan(plan)
        rep = self.env.export_replay()
        for key in ("run_id", "config_hash", "seed", "turns", "stats", "final_state_hash"):
            self.assertIn(key, rep)
        self.assertIn("repeat_coin_count", rep["stats"])


if __name__ == "__main__":
    unittest.main()
