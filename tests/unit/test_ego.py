"""E.G.O 验证 —— 按 wiki.gg 原文重写（docs/audit_report.md §1 / §4）。

核心：**只有 Solemn Lament Gregor 与 Harmony Sinclair 带 Coin Reuse**；
Solemn Lament Yi Sang **没有** Coin Reuse，它靠 5 枚 Unbreakable 硬币 + 蝶结算。
"""

from __future__ import annotations

import unittest

from helpers import CONTENT
from rr6sim.core.config import SimConfig
from rr6sim.core.engine import Battle
from rr6sim.core.enums import DamageType, Side, SlotKind
from rr6sim.core.state import BattleState


def real_battle(**cfg_kw):
    cfg = SimConfig(**cfg_kw).normalized()
    allies, enemies = CONTENT.make_encounter(cfg)
    st = BattleState(allies=allies, enemies=enemies, config=cfg, seed=0, rng_state=0)
    b = Battle(st, CONTENT)
    b.log_enabled = True
    for u in allies:
        u.has_sanity = True
    return b, {u.uid: u for u in allies}, {u.uid: u for u in enemies}


def coin_log(b):
    return [e for e in b.state.log if e.get("kind") == "coin"]


def use_ego(battle, unit, eid, target_uid="boss", overclock=False, slot_index=0):
    slot = unit.slots[slot_index]
    battle.assign_action(slot, "ego", eid, overclock)
    battle.assign_target(slot, target_uid, 0)
    battle.execute_slot(unit, slot)
    return slot


class TestCoinReuseMechanics(unittest.TestCase):
    def test_gregor_solemn_lament_reuses_coin3(self):
        """[On Hit] At 0+ SP, Reuse this Coin (5 times max per Skill)。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["lantern_gregor"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_gregor")
        # 3 枚硬币 + 第 3 枚最多 reuse 5 次 = 8 次命中
        self.assertEqual(len(coin_log(b)), 8)
        self.assertEqual(b.counters.get("reuse_count"), 5)
        self.assertLess(u.sp, 45)   # 每次 reuse 命中 -2~6 SP

    def test_gregor_reuse_stops_when_sp_negative(self):
        """条件必须**每次 reuse 前重新判定**：SP 变负后不再 reuse。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["lantern_gregor"]
        u.sp = 0
        # 第 3 枚硬币命中后 SP 变成负数 → 不应再 reuse
        use_ego(b, u, "solemn_lament_gregor")
        self.assertEqual(b.counters.get("reuse_count", 0), 0)
        self.assertEqual(len(coin_log(b)), 3)

    def test_harmony_reuses_on_heads_hit_with_hp_gate(self):
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["band_sinclair"]
        u.sp = 45
        hp0 = u.hp
        use_ego(b, u, "harmony_sinclair")
        # 3 枚硬币 + 第 3 枚 reuse 最多 4 次 = 7 次命中
        self.assertEqual(len(coin_log(b)), 7)
        self.assertEqual(b.counters.get("reuse_count"), 4)
        self.assertLess(u.hp, hp0)                       # 自伤
        self.assertGreater(b.counters.get("self_harm", 0), 0)

    def test_harmony_stops_at_low_hp(self):
        """HP < 10% 时不应再 reuse/自伤。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["band_sinclair"]
        u.sp = 45
        u.hp = int(u.max_hp * 0.05)
        use_ego(b, u, "harmony_sinclair")
        self.assertEqual(b.counters.get("reuse_count", 0), 0)

    def test_reuse_only_repeats_the_targeted_coin(self):
        """reuse 只重复**指定的那一枚**硬币，不是整个技能重打一遍。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["lantern_gregor"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_gregor")
        coins = {e["coin"] for e in coin_log(b)}
        self.assertEqual(coins, {0, 1, 2})
        reuse_counts = {}
        for e in coin_log(b):
            if e["reuse"]:
                reuse_counts[e["coin"]] = reuse_counts.get(e["coin"], 0) + 1
        self.assertEqual(reuse_counts, {2: 5})   # 只有第 3 枚（index 2）被 reuse

    def test_reuse_retriggers_on_hit_effects(self):
        """reuse 的硬币会重新触发 [On Hit]（蝶施加次数随之增加）。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["lantern_gregor"]
        u.sp = 45
        before = b.counters.get("butterfly_inflicted", 0)
        use_ego(b, u, "solemn_lament_gregor")
        after = b.counters.get("butterfly_inflicted", 0)
        self.assertGreaterEqual(after - before, 8)   # 8 次命中各施加蝶

    def test_coin_reuse_can_be_disabled(self):
        """消融 E：关闭 Coin Reuse。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", coin_reuse_enabled=False,
                                         corrosion_mode="never")
        u = allies["lantern_gregor"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_gregor")
        self.assertEqual(len(coin_log(b)), 3)
        self.assertEqual(b.counters.get("reuse_count", 0), 0)


class TestYiSangSolemnLament(unittest.TestCase):
    def test_has_no_coin_reuse(self):
        """李箱庄严哀悼**不在** Category:E.G.O with Coin Reuse 中。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["solemn_yisang"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_yisang")
        self.assertEqual(b.counters.get("reuse_count", 0), 0)
        self.assertEqual(len(coin_log(b)), 5)     # 5 枚硬币各一次

    def test_five_unbreakable_coins(self):
        ego = CONTENT.ego("solemn_lament_yisang")
        self.assertTrue(all(c.unbreakable for c in ego.awakening.coins))
        self.assertEqual(len(ego.awakening.coins), 5)

    def test_inflicts_butterfly_and_sinking_count(self):
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        boss = enemies["boss"]
        u = allies["solemn_yisang"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_yisang")
        self.assertGreater(b.counters.get("butterfly_inflicted", 0), 0)
        self.assertGreater(boss.status_count("sinking") + boss.status_potency("sinking"), 0)

    def test_coin5_spends_living_and_departed(self):
        """第 5 枚硬币花光 The Living & The Departed 并结算 Gloom 追加伤害。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        boss = enemies["boss"]
        boss.set_status("butterfly", potency=10, count=10)
        u = allies["solemn_yisang"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_yisang")
        self.assertGreater(b.counters.get("butterfly_spent", 0), 0)
        # 花光后第 5 枚硬币又按原文施加了 2 Living + 2 Departed
        self.assertGreater(boss.status_potency("butterfly") + boss.status_count("butterfly"), 0)
        self.assertLess(boss.status_potency("butterfly") + boss.status_count("butterfly"), 20)


class TestEgoCostAndCorrosion(unittest.TestCase):
    def test_awakening_cost(self):
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["solemn_yisang"]
        u.sp = 30
        use_ego(b, u, "solemn_lament_yisang")
        # 30 - 20（觉醒消耗） + 5（硬币施加蝶后，后续硬币命中触发蝶的攻击者回 SP）
        self.assertEqual(u.sp, 15)

    def test_low_sp_does_not_block_ego(self):
        """低 SP 不再让 E.G.O 不可用（真实规则）。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["solemn_yisang"]
        u.sp = 5
        ids = [a["id"] for a in b.legal_actions(u.slots[0]) if a["kind"] == "ego"]
        self.assertIn("solemn_lament_yisang", ids)

    def test_forced_corrosion_when_reaching_minus_45(self):
        """SP 消耗后 ≤ −45 → 必定侵蚀，并按侵蚀技能的 SP 消耗扣。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="rng")
        u = allies["solemn_yisang"]
        u.sp = -30
        use_ego(b, u, "solemn_lament_yisang")
        self.assertEqual(b.counters.get("ego_corrosion"), 1)
        self.assertEqual(u.sp, -45)          # -30 - 25（corrosion cost）→ clamp -45

    def test_overclock_costs_one_and_a_half(self):
        """Overclock：花 1.5× 觉醒 SP 消耗，得到侵蚀技能（稳定目标）。"""
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["solemn_yisang"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_yisang", overclock=True)
        self.assertEqual(b.counters.get("ego_overclock"), 1)
        self.assertEqual(u.sp, 45 - 30)      # ceil(20 × 1.5) = 30

    def test_same_ego_cannot_be_used_twice_in_a_turn(self):
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["solemn_yisang"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_yisang")
        ids = [a["id"] for a in b.legal_actions(u.slots[0]) if a["kind"] == "ego"]
        self.assertNotIn("solemn_lament_yisang", ids)

    def test_resist_override_uses_ego_table(self):
        b, allies, enemies = real_battle(coin_mode="always_heads", corrosion_mode="never")
        u = allies["solemn_yisang"]
        u.sp = 45
        use_ego(b, u, "solemn_lament_yisang")
        # 该 E.G.O 的忧郁抗性 = Ineff.(0.5)
        self.assertAlmostEqual(u.resistance_value(__import__("rr6sim.core.enums",
                                                             fromlist=["Sin"]).Sin.GLOOM), 0.5)


if __name__ == "__main__":
    unittest.main()
