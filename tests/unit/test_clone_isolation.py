"""clone 深复制隔离 + transition/observation hash（审计 §6，搜索前置条件）。

搜索（Beam / MCTS / 置换表）的前提：
* clone 之后改动任何嵌套结构都不能污染原状态；
* transition_hash 必须覆盖一切会影响未来状态转移的信息
  （RNG 状态、技能牌堆、Boss 隐藏状态、flags…）；
* observation_hash 只反映玩家可见信息。
"""

from __future__ import annotations

import unittest

from helpers import CONTENT, all_heads, attack, make_battle, make_skill, make_unit
from rr6sim import SimConfig
from rr6sim.core.enums import Side
from rr6sim.search.greedy import greedy_plan
from rr6sim.simulate import apply_plan, new_battle


class TestCloneIsolation(unittest.TestCase):
    def setUp(self):
        self.battle = new_battle(CONTENT, SimConfig(boss_hp_scale=0.5), seed=3)
        self.battle.state.flags["targeted_phantoms"] = ["phantom_past"]
        self.battle.state.deck_queue["solemn_yisang"] = ["yi_s1", "yi_s2", "yi_s3"]
        self.clone = self.battle.clone()

    def test_flags_nested_list(self):
        self.clone.state.flags["targeted_phantoms"].append("phantom_future")
        self.assertEqual(self.battle.state.flags["targeted_phantoms"], ["phantom_past"])

    def test_deck_queue(self):
        self.clone.state.deck_queue["solemn_yisang"].append("yi_s1")
        self.assertEqual(self.battle.state.deck_queue["solemn_yisang"], ["yi_s1", "yi_s2", "yi_s3"])

    def test_unit_state_nested(self):
        ally = self.clone.state.allies[0]
        ally.state["nested"] = {"a": [1, 2]}
        ally.state["nested"]["a"].append(3)
        ally.state["egos_used_this_turn"].append("solemn_lament_yisang")
        self.assertNotIn("nested", self.battle.state.allies[0].state)
        self.assertEqual(self.battle.state.allies[0].state["egos_used_this_turn"], [])

    def test_unit_res(self):
        ally = self.clone.state.allies[0]
        ally.res["living_butterfly"] = 7
        ally.res["new_key"] = 9
        self.assertNotEqual(self.battle.state.allies[0].res.get("living_butterfly"), 7)
        self.assertNotIn("new_key", self.battle.state.allies[0].res)

    def test_statuses(self):
        boss = self.clone.boss()
        boss.add_status("sinking", potency=5, count=5)
        self.assertEqual(self.battle.boss().status_potency("sinking"), 0)

    def test_slots(self):
        slot = self.clone.state.allies[0].slots[0]
        slot.choice_id = "yi_s3"
        slot.target_uid = "boss"
        self.assertEqual(self.battle.state.allies[0].slots[0].choice_id, "")

    def test_branch_simulation_does_not_pollute(self):
        plan_a = greedy_plan(self.battle)
        b1 = self.battle.clone()
        apply_plan(b1, plan_a)
        b1.resolve_turn()
        # 原战斗不受影响
        self.assertEqual(self.battle.state.turn, 1)
        self.assertEqual(self.battle.boss().hp, self.battle.state.enemies[0].max_hp)


class TestHashSemantics(unittest.TestCase):
    def test_transition_hash_includes_rng_state(self):
        b1 = new_battle(CONTENT, SimConfig(boss_hp_scale=0.5), seed=1)
        b2 = b1.clone()
        self.assertEqual(b1.state.transition_hash(), b2.state.transition_hash())
        b2.rng.state ^= 0x123456789
        b2.sync()
        self.assertNotEqual(b1.state.transition_hash(), b2.state.transition_hash())

    def test_transition_hash_includes_deck_queue(self):
        b1 = new_battle(CONTENT, SimConfig(boss_hp_scale=0.5), seed=1)
        b2 = b1.clone()
        b2.state.deck_queue["solemn_yisang"] = ["yi_s3"]
        self.assertNotEqual(b1.state.transition_hash(), b2.state.transition_hash())

    def test_transition_hash_includes_flags(self):
        b1 = new_battle(CONTENT, SimConfig(boss_hp_scale=0.5), seed=1)
        b2 = b1.clone()
        b2.state.flags["targeted_phantoms"] = ["phantom_past"]
        self.assertNotEqual(b1.state.transition_hash(), b2.state.transition_hash())

    def test_observation_hash_ignores_hidden_state(self):
        b1 = new_battle(CONTENT, SimConfig(boss_hp_scale=0.5), seed=1)
        b2 = b1.clone()
        self.assertEqual(b1.state.observation_hash(), b2.state.observation_hash())
        b2.rng.state ^= 0xABCDEF
        b2.sync()
        b2.state.deck_queue["solemn_yisang"] = ["yi_s1"]
        b2.state.flags["hidden_flag"] = True
        self.assertEqual(b1.state.observation_hash(), b2.state.observation_hash())
        self.assertNotEqual(b1.state.transition_hash(), b2.state.transition_hash())

    def test_state_hash_is_transition_hash(self):
        b = new_battle(CONTENT, SimConfig(boss_hp_scale=0.5), seed=1)
        self.assertEqual(b.state.hash(), b.state.transition_hash())

    def test_visible_change_changes_observation_hash(self):
        b1 = new_battle(CONTENT, SimConfig(boss_hp_scale=0.5), seed=1)
        b2 = b1.clone()
        b2.boss().hp -= 100
        self.assertNotEqual(b1.state.observation_hash(), b2.state.observation_hash())


class TestDeck(unittest.TestCase):
    def test_deck_counts_are_three_two_one(self):
        for key, ident in CONTENT.identities.items():
            counts = sorted(ident.deck_counts.values(), reverse=True)
            self.assertEqual(counts, [3, 2, 1], f"{key} 牌堆份数应为 3/2/1")
            self.assertEqual(len(ident.deck), 6)

    def test_expanded_deck_multiset(self):
        ident = CONTENT.identity("solemn_yisang")
        from collections import Counter

        self.assertEqual(Counter(ident.deck), {"yi_s1": 3, "yi_s2": 2, "yi_s3": 1})

    def test_fixed_mode_draws_are_reproducible(self):
        cfg = SimConfig(speed_mode="fixed", skill_draw_mode="fixed", coin_mode="script",
                        coin_script=[True], boss_hp_scale=0.5)
        a = new_battle(CONTENT, cfg, seed=7)
        b = new_battle(CONTENT, cfg, seed=7)
        da = {u.uid: [list(s.skill_choices) for s in u.slots] for u in a.state.allies}
        db = {u.uid: [list(s.skill_choices) for s in u.slots] for u in b.state.allies}
        self.assertEqual(da, db)
        self.assertEqual(a.state.transition_hash(), b.state.transition_hash())

    def test_rng_mode_same_seed_same_draw(self):
        cfg = SimConfig(coin_mode="rng", boss_hp_scale=0.5)
        a = new_battle(CONTENT, cfg, seed=11)
        b = new_battle(CONTENT, cfg, seed=11)
        da = {u.uid: [list(s.skill_choices) for s in u.slots] for u in a.state.allies}
        db = {u.uid: [list(s.skill_choices) for s in u.slots] for u in b.state.allies}
        self.assertEqual(da, db)

    def test_deck_refreshes_only_after_being_exhausted(self):
        """一副牌抽完之前不会重新洗牌（wiki.gg/Battles）。"""
        cfg = SimConfig(speed_mode="fixed", skill_draw_mode="fixed", coin_mode="script",
                        coin_script=[True], boss_hp_scale=0.5)
        b = new_battle(CONTENT, cfg, seed=1)
        ident = CONTENT.identity("solemn_yisang")
        # 3 回合（每回合 1 槽抽 2 张）刚好抽完一副 6 张的牌
        seen = []
        for _ in range(3):
            seen.extend(b.state.allies[0].slots[0].skill_choices)
            key = b.state.allies[0].identity
            plan = greedy_plan(b)
            apply_plan(b, plan)
            b.resolve_turn()
            if not b.state.is_terminal():
                b.begin_turn()
        from collections import Counter

        self.assertEqual(Counter(seen), {"yi_s1": 3, "yi_s2": 2, "yi_s3": 1})


if __name__ == "__main__":
    unittest.main()
