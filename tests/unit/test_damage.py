"""伤害公式 / 拼点 / 混乱 的最小验证 —— 按 wiki.gg 的真实公式重写。

公式（docs/audit_report.md §2）：

    Final = Coin Roll × (1 + Static) × (1 + Dynamic)
    Static = Sin Res Mod + Damage Res Mod + Off/Def Level Advantage + Crit
             + Clash Count × 0.03 + Observation Level
    抗性分段：x<0 → -0.5 / 0≤x<1 → (x-1)/2 / x≥1 → x-1
    攻防等级：M = (Off - Def) / (|Off - Def| + 25)
    混乱：物理抗性被替换为 (Stagger Level × 0.5 + 0.5)
    取整：向下，最低 1；且不低于 0.05 × Coin Roll
"""

from __future__ import annotations

import unittest

from helpers import all_heads, attack, make_battle, make_skill, make_unit
from rr6sim.core.config import SimConfig
from rr6sim.core.damage import offense_defense_modifier, resistance_modifier
from rr6sim.core.enums import DamageType, Side, Sin


class TestResistanceModifier(unittest.TestCase):
    def test_piecewise(self):
        self.assertAlmostEqual(resistance_modifier(0.0), -0.5)
        self.assertAlmostEqual(resistance_modifier(0.5), -0.25)
        self.assertAlmostEqual(resistance_modifier(1.0), 0.0)
        self.assertAlmostEqual(resistance_modifier(1.5), 0.5)
        self.assertAlmostEqual(resistance_modifier(2.0), 1.0)


class TestLevelModifier(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(offense_defense_modifier(50, 50), 0.0)
        self.assertAlmostEqual(offense_defense_modifier(53, 50), 3 / 28)
        self.assertAlmostEqual(offense_defense_modifier(50, 53), -3 / 28)
        self.assertAlmostEqual(offense_defense_modifier(60, 50), 10 / 35)


class TestDamageFormula(unittest.TestCase):
    def _one_coin(self, *, base=5, power=3, **unit_kw):
        sk = make_skill("t_f", coins=1, power=power, damage=0, base_power=base,
                        damage_type="slash", sin="wrath")
        a = make_unit("a", Side.ALLY, **{k: v for k, v in unit_kw.items() if k in ("offense", "sp")})
        e = make_unit("e", Side.ENEMY, hp=999, **{k: v for k, v in unit_kw.items()
                                                  if k in ("defense",)})
        return sk, a, e

    def test_coin_roll_is_the_damage_base(self):
        sk, a, e = self._one_coin()
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 8)  # 5 + 3

    def test_heads_and_tails_change_coin_roll(self):
        sk = make_skill("t_f2", coins=1, power=4, damage=0, base_power=6)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], SimConfig(coin_mode="always_tails"))
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 6)  # 反面不加硬币威力

    def test_offense_defense_level_advantage(self):
        sk = make_skill("t_f3", coins=1, power=0, damage=0, base_power=10)
        a = make_unit("a", Side.ALLY, offense=60)
        e = make_unit("e", Side.ENEMY, hp=999, defense=50)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - int(10 * (1 + 10 / 35)))

    def test_skill_offense_level_modifier(self):
        sk = make_skill("t_f4", coins=1, power=0, damage=0, base_power=10, offense_level_mod=5)
        a = make_unit("a", Side.ALLY, offense=50)
        e = make_unit("e", Side.ENEMY, hp=999, defense=50)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - int(10 * (1 + 5 / 30)))

    def test_sin_resistance_is_piecewise(self):
        sk = make_skill("t_f5", coins=1, power=0, damage=0, base_power=8, sin="gloom")
        for res, expected_mod in ((0.5, -0.25), (1.5, 0.5), (2.0, 1.0), (0.0, -0.5)):
            a = make_unit("a", Side.ALLY)
            e = make_unit("e", Side.ENEMY, hp=999)
            e.sin_resistances[Sin.GLOOM] = res
            b = make_battle([a], [e], all_heads())
            attack(b, a, e, sk)
            self.assertEqual(e.hp, 999 - int(8 * (1 + expected_mod)), f"res={res}")

    def test_damage_type_resistance(self):
        sk = make_skill("t_f6", coins=1, power=0, damage=0, base_power=8, damage_type="pierce")
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.resistances[DamageType.PIERCE] = 1.5
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 12)

    def test_minimum_damage_rules(self):
        """向下取整、最低 1、且不低于 0.05 × Coin Roll。"""
        sk = make_skill("t_f7", coins=1, power=0, damage=0, base_power=40, sin="gloom")
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.sin_resistances[Sin.GLOOM] = 0.5   # -25%
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        # 40 × 0.75 = 30（远高于最低值）
        self.assertEqual(e.hp, 999 - 30)

    def test_synthetic_coin_damage_acts_as_attack_adder(self):
        sk = make_skill("t_f8", coins=1, power=0, damage=7, base_power=5)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 12)

    def test_multiple_coins_are_independent(self):
        sk = make_skill("t_f9", coins=4, power=0, damage=0, base_power=5)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 20)


class TestClash(unittest.TestCase):
    def _clash(self, a_skill, b_skill, cfg=None):
        a = make_unit("a", Side.ALLY, hp=500)
        e = make_unit("e", Side.ENEMY, hp=500)
        b = make_battle([a], [e], cfg or all_heads())
        winner, kept, a_cracked, b_cracked = b._clash_advance(a, a_skill, e, b_skill)
        return b, a, e, winner, kept, a_cracked, b_cracked

    def test_winner_keeps_coins_loser_destroyed(self):
        a_sk = make_skill("t_c1", coins=3, power=5, damage=0, base_power=10)
        b_sk = make_skill("t_c2", coins=3, power=0, damage=0, base_power=1)
        b, a, e, winner, kept, ac, bc = self._clash(a_sk, b_sk)
        self.assertEqual(winner, "a")
        self.assertEqual(len(kept), 3)
        self.assertEqual(bc, {})

    def test_tie_destroys_both(self):
        a_sk = make_skill("t_c3", coins=1, power=0, damage=0, base_power=10)
        b_sk = make_skill("t_c4", coins=1, power=0, damage=0, base_power=10)
        b, a, e, winner, kept, ac, bc = self._clash(a_sk, b_sk)
        self.assertEqual(winner, "draw")
        self.assertEqual(kept, {})

    def test_unbreakable_coin_becomes_cracked_not_destroyed(self):
        """Unbreakable Coin：拼点失败 → Cracked，仍会在失败后结算。"""
        a_sk = make_skill("t_c5", coins=2, power=0, damage=0, base_power=20)
        b_sk = make_skill("t_c6", coins=2, power=0, damage=0, base_power=1)
        b_sk.coins[0].unbreakable = True
        b_sk.coins[1].unbreakable = True
        b, a, e, winner, kept, ac, bc = self._clash(a_sk, b_sk)
        self.assertEqual(winner, "a")           # b 的硬币没被破坏而是 cracked
        self.assertEqual(sorted(bc), [0, 1])    # 两枚都 cracked 保留
        # 输方只用 cracked 硬币结算，且威力固定 +1（正面硬币）
        self.assertEqual(b.coin_power(e, b_sk, 0, heads=True, cracked=True), b_sk.base_power + 1)

    def test_clash_level_bonus_one_per_three_levels(self):
        """Battles 页：高等级方每 3 级差获得 +1 拼点威力（向下取整）。"""
        a_sk = make_skill("t_c7", coins=1, power=0, damage=0, base_power=5)
        a = make_unit("a", Side.ALLY, offense=53)
        e = make_unit("e", Side.ENEMY, hp=100, offense=50)
        b = make_battle([a], [e], all_heads())
        # 等级差 3 → +1
        self.assertEqual(b.clash_value(a, a_sk, 0, heads=False, opponent=e), 6)
        self.assertEqual(b.clash_value(e, a_sk, 0, heads=False, opponent=a), 5)


class TestStagger(unittest.TestCase):
    def test_stagger_replaces_physical_resistance(self):
        sk = make_skill("t_s1", coins=1, power=0, damage=0, base_power=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.staggered = True
        e.stagger_level = 1
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        # 物理抗性被替换为 (1×0.5+0.5)=+1 → ×2
        self.assertEqual(e.hp, 999 - 20)

    def test_stagger_level_scales(self):
        for level, mult in ((1, 2.0), (2, 2.5), (3, 3.0)):
            a = make_unit("a", Side.ALLY)
            e = make_unit("e", Side.ENEMY, hp=999)
            e.staggered = True
            e.stagger_level = level
            sk = make_skill(f"t_s2_{level}", coins=1, power=0, damage=0, base_power=10)
            b = make_battle([a], [e], all_heads())
            attack(b, a, e, sk)
            self.assertEqual(e.hp, 999 - int(10 * mult), f"level={level}")

    def test_threshold_crossing_raises_level_once_per_call(self):
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=100)
        e.stagger_thresholds = [80, 50]
        sk = make_skill("t_s3", coins=1, power=0, damage=0, base_power=60)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertTrue(e.staggered)
        self.assertEqual(e.stagger_index, 2)
        self.assertEqual(e.stagger_level, 1)

    def test_stagger_change_already_weak_resistance_keeps_higher(self):
        """混乱不与此前已有的弱点叠加（取较高者）。"""
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.resistances[DamageType.SLASH] = 2.0   # Fatal → +1
        e.staggered = True
        e.stagger_level = 1                      # 也是 +1
        sk = make_skill("t_s4", coins=1, power=0, damage=0, base_power=10, damage_type="slash")
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 20)


if __name__ == "__main__":
    unittest.main()
