"""E.G.O 规则验证：SP 消耗 / 合法性 / 抗性覆盖 / 重复硬币。"""

from __future__ import annotations

import unittest

from helpers import CONTENT, all_heads, attack, coin_log, make_battle, make_skill, make_unit
from rr6sim.core.config import SimConfig
from rr6sim.core.enums import Side, Sin, SlotKind


def real_battle(**cfg_kw):
    cfg = SimConfig(**cfg_kw).normalized()
    allies, enemies = CONTENT.make_encounter(cfg)
    from rr6sim.core.engine import Battle
    from rr6sim.core.state import BattleState

    st = BattleState(allies=allies, enemies=enemies, config=cfg, seed=0, rng_state=0)
    b = Battle(st, CONTENT)
    return b, {u.uid: u for u in allies}, {u.uid: u for u in enemies}


class TestEgoBasics(unittest.TestCase):
    def test_sp_cost_is_paid(self):
        b, allies, _ = real_battle(coin_mode="always_heads")
        u = allies["solemn_yisang"]
        u.sp = 25
        slot = u.slots[0]
        b.assign_action(slot, "ego", "solemn_lament_yisang", False)
        b.assign_target(slot, "boss", 0)
        b.execute_slot(u, slot)
        self.assertEqual(u.sp, 0)
        self.assertEqual(b.counters.get("ego_use"), 1)

    def test_corrosion_costs_more(self):
        b, allies, _ = real_battle(coin_mode="always_heads")
        u = allies["solemn_yisang"]
        u.sp = 40
        slot = u.slots[0]
        b.assign_action(slot, "ego", "solemn_lament_yisang", True)
        b.assign_target(slot, "boss", 0)
        b.execute_slot(u, slot)
        self.assertEqual(u.sp, 40 - 35)

    def test_ego_not_offered_without_sp(self):
        b, allies, _ = real_battle()
        u = allies["solemn_yisang"]
        u.sp = 5
        slot = u.slots[0]
        ids = [a["id"] for a in b.legal_actions(slot) if a["kind"] == "ego"]
        self.assertNotIn("solemn_lament_yisang", ids)
        u.sp = 25
        ids = [a["id"] for a in b.legal_actions(slot) if a["kind"] == "ego"]
        self.assertIn("solemn_lament_yisang", ids)

    def test_disabled_ego_is_not_equipped(self):
        b, allies, _ = real_battle(disabled_egos=["solemn_lament_yisang"])
        self.assertNotIn("solemn_lament_yisang", allies["solemn_yisang"].ego_ids)

    def test_resist_override_applies_for_the_turn(self):
        b, allies, _ = real_battle(coin_mode="always_heads")
        u = allies["solemn_yisang"]
        u.sp = 25
        slot = u.slots[0]
        before = u.resistance_for_test if False else u.resistance
        from rr6sim.core.enums import DamageType

        base_wrath = u.resistance(DamageType.SLASH, Sin.WRATH)
        b.assign_action(slot, "ego", "solemn_lament_yisang", False)
        b.assign_target(slot, "boss", 0)
        b.execute_slot(u, slot)
        self.assertEqual(u.resist_override.get("_all_from_sin"), "gloom")
        after_wrath = u.resistance(DamageType.SLASH, Sin.WRATH)
        # 使用 E.G.O 后，罪孽抗性被替换为该 E.G.O 属性（忧郁）的抗性
        self.assertAlmostEqual(after_wrath, u.sin_resistances[Sin.GLOOM])
        self.assertNotAlmostEqual(base_wrath, after_wrath)


class TestRepeatCoin(unittest.TestCase):
    def _run_ego_against_boss_with_sinking(self, potency: int, **cfg_kw):
        b, allies, enemies = real_battle(coin_mode="always_heads", **cfg_kw)
        boss = enemies["boss"]
        boss.set_status("sinking", potency, 99)
        u = allies["solemn_yisang"]
        u.sp = 25
        slot = u.slots[0]
        b.assign_action(slot, "ego", "solemn_lament_yisang", False)
        b.assign_target(slot, "boss", 0)
        b.log_enabled = True
        b.execute_slot(u, slot)
        return b, boss

    def test_repeat_coin_requires_sinking_potency(self):
        """沉沦强度不足时不会重复投掷。"""
        b, boss = self._run_ego_against_boss_with_sinking(0)
        self.assertEqual(b.counters.get("repeat_coin", 0), 0)
        self.assertEqual(len(coin_log(b)), 4)

    def test_repeat_coin_scales_with_sinking(self):
        """每 10 点沉沦强度重复 1 次，最多 2 次 -> 4 枚硬币变成 12 次命中。"""
        b, boss = self._run_ego_against_boss_with_sinking(20)
        self.assertEqual(len(coin_log(b)), 12)
        self.assertEqual(b.counters.get("repeat_coin"), 8)

    def test_repeat_coin_can_be_disabled(self):
        """消融 E：关闭重复硬币。"""
        b, boss = self._run_ego_against_boss_with_sinking(20, repeat_coin_enabled=False)
        self.assertEqual(len(coin_log(b)), 4)

    def test_repeated_coins_trigger_on_hit_effects_again(self):
        """重复投掷必须重新触发「命中时」效果（计划书 §18.1）。"""
        b, boss = self._run_ego_against_boss_with_sinking(20)
        # 每枚硬币 on_hit 施加 1 层沉沦强度 2 -> 12 次命中
        self.assertGreaterEqual(boss.status_potency("sinking"), 20 + 12 * 2)


class TestEgoSkills(unittest.TestCase):
    def test_harmony_repeat_consumes_resource(self):
        b, allies, enemies = real_battle(coin_mode="always_heads")
        u = allies["band_sinclair"]
        u.sp = 25
        u.res["harmony"] = 3
        slot = u.slots[0]
        b.assign_action(slot, "ego", "harmony_sinclair", False)
        b.assign_target(slot, "boss", 0)
        b.log_enabled = True
        b.execute_slot(u, slot)
        self.assertEqual(u.res["harmony"], 0)
        self.assertEqual(len(coin_log(b)), 6)  # 3 枚硬币 × 2 次投掷

    def test_harmony_without_resource_does_not_repeat(self):
        b, allies, enemies = real_battle(coin_mode="always_heads")
        u = allies["band_sinclair"]
        u.sp = 25
        u.res["harmony"] = 1
        slot = u.slots[0]
        b.assign_action(slot, "ego", "harmony_sinclair", False)
        b.assign_target(slot, "boss", 0)
        b.log_enabled = True
        b.execute_slot(u, slot)
        self.assertEqual(len(coin_log(b)), 3)


if __name__ == "__main__":
    unittest.main()
