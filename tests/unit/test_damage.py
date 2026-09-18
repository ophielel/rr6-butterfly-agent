"""伤害 / 拼点 / 混乱 的最小验证（计划书 §18.1）。"""

from __future__ import annotations

import unittest

from helpers import CONTENT, all_heads, attack, make_battle, make_skill, make_unit
from rr6sim.core.enums import DamageType, Side, Sin, TargetMode
from rr6sim.core.config import SimConfig


class TestDamage(unittest.TestCase):
    def test_coin_damage_hand_calc(self):
        """硬币伤害 = (硬币伤害 + 硬币威力) × 等级倍率 × 抗性。"""
        sk = make_skill("t_dmg1", coins=1, power=4, damage=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        # 10 + 4 = 14；等级差 0 -> ×1.0；抗性 1.0
        self.assertEqual(e.hp, 999 - 14)

    def test_resistance_and_level(self):
        sk = make_skill("t_dmg2", coins=1, power=0, damage=10, damage_type="pierce")
        a = make_unit("a", Side.ALLY, offense=60)
        e = make_unit("e", Side.ENEMY, hp=999, defense=50)
        e.resistances[DamageType.PIERCE] = 2.0
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        # 10 × (1 + 0.03*10) × 2.0 = 26
        self.assertEqual(e.hp, 999 - 26)

    def test_sin_resistance_applies(self):
        sk = make_skill("t_dmg3", coins=1, power=0, damage=10, sin="gloom")
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.sin_resistances[Sin.GLOOM] = 0.5
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 5)

    def test_multi_coin_deals_per_coin(self):
        sk = make_skill("t_dmg4", coins=4, power=0, damage=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 40)

    def test_positive_coin_tails_loses_power(self):
        sk = make_skill("t_dmg5", coins=1, power=6, damage=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], SimConfig(coin_mode="always_tails"))
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 10)

    def test_negative_coin_tails_gains_power(self):
        sk = make_skill("t_dmg6", coins=1, power=6, damage=10, coin_kind="negative")
        a = make_unit("a", Side.ALLY, sp=-30)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], SimConfig(coin_mode="always_tails"))
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 16)

    def test_coin_power_can_be_excluded_from_damage(self):
        sk = make_skill("t_dmg7", coins=1, power=6, damage=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], SimConfig(coin_mode="always_heads", coin_power_adds_damage=False))
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 10)


class TestClash(unittest.TestCase):
    def _clash(self, a_skill, b_skill, *, a_power_heads=True, b_power_heads=True, cfg=None):
        a = make_unit("a", Side.ALLY, hp=200)
        e = make_unit("e", Side.ENEMY, hp=200)
        b = make_battle([a], [e], cfg or all_heads())
        a.slots[0].choice_kind = a.slots[0].choice_kind
        # 直接调用拼点
        winner, kept = b._clash_advance(a, a_skill, e, b_skill)
        return b, a, e, winner, kept

    def test_clash_winner_destroys_loser_coins(self):
        """3 硬币 vs 3 硬币，A 全胜 -> A 用 3 枚硬币攻击，B 全部被破坏。"""
        a_sk = make_skill("t_c1a", coins=3, power=5, damage=10, base_power=10)
        b_sk = make_skill("t_c1b", coins=3, power=0, damage=10, base_power=1)
        b, a, e, winner, kept = self._clash(a_sk, b_sk)
        self.assertEqual(winner, "a")
        self.assertEqual(len(kept), 3)

    def test_clash_tie_destroys_both(self):
        a_sk = make_skill("t_c2a", coins=1, power=0, damage=10, base_power=10)
        b_sk = make_skill("t_c2b", coins=1, power=0, damage=10, base_power=10)
        b, a, e, winner, kept = self._clash(a_sk, b_sk)
        self.assertEqual(winner, "draw")
        self.assertEqual(kept, {})

    def test_fewer_coins_loses_in_advance_model(self):
        a_sk = make_skill("t_c3a", coins=1, power=99, damage=10, base_power=99)
        b_sk = make_skill("t_c3b", coins=3, power=0, damage=10, base_power=1)
        b, a, e, winner, kept = self._clash(a_sk, b_sk)
        self.assertEqual(winner, "b")

    def test_reflex_model_single_coin_wins(self):
        """reflex 模型下高威力单硬币技能可以连续拼掉多枚硬币。"""
        a_sk = make_skill("t_c4a", coins=1, power=99, damage=10, base_power=99)
        b_sk = make_skill("t_c4b", coins=3, power=0, damage=10, base_power=1)
        b = make_battle([make_unit("a", Side.ALLY), ], [make_unit("e", Side.ENEMY)],
                        SimConfig(coin_mode="always_heads", clash_model="reflex"))
        winner, _ = b._clash_reflex(b.unit("a"), a_sk, b.unit("e"), b_sk)
        self.assertEqual(winner, "a")

    def test_clash_win_gains_sp(self):
        a_sk = make_skill("t_c5a", coins=3, power=5, damage=10, base_power=10)
        b_sk = make_skill("t_c5b", coins=1, power=0, damage=10, base_power=1)
        a = make_unit("a", Side.ALLY, hp=200, sp=0)
        e = make_unit("e", Side.ENEMY, hp=200, sp=0)
        b = make_battle([a], [e], all_heads())
        a.slots[0].choice_id = a_sk.sid
        e.slots[0].choice_id = b_sk.sid
        e.slots[0].target_uid = "a"
        e.slots[0].target_slot = 0
        b.execute_clash(a, a.slots[0], a_sk, e, e.slots[0])
        self.assertEqual(a.sp, 1)


class TestStagger(unittest.TestCase):
    def test_stagger_threshold_triggers_once_and_cancels_slots(self):
        sk = make_skill("t_st1", coins=1, power=0, damage=80)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=100)
        e.stagger_thresholds = [50]
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertTrue(e.staggered)
        self.assertEqual(e.stagger_index, 1)
        self.assertTrue(e.slots[0].cancelled)
        # 混乱状态下再次受击不会再触发一次
        attack(b, a, e, make_skill("t_st2", coins=1, power=0, damage=10))
        self.assertEqual(e.stagger_index, 1)

    def test_staggered_takes_more_damage(self):
        sk = make_skill("t_st3", coins=1, power=0, damage=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.staggered = True
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 15)  # 1.5x


if __name__ == "__main__":
    unittest.main()
