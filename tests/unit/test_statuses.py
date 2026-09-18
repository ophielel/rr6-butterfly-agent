"""状态触发时点验证（计划书 §18.1：每一个机制都做最小测试）。"""

from __future__ import annotations

import unittest

from helpers import all_heads, attack, make_battle, make_skill, make_unit
from rr6sim.core.config import SimConfig
from rr6sim.core.enums import Side, Timing


class TestSinking(unittest.TestCase):
    def test_sinking_triggers_per_coin_and_consumes_count(self):
        """沉沦：每次命中损失等同强度的精神力，层数 -1。"""
        sk = make_skill("t_sk1", coins=3, power=0, damage=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("sinking", potency=3, count=2)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.sp, -6)          # 2 次触发 × 强度 3
        self.assertEqual(e.status_count("sinking"), 0)

    def test_sinking_triggers_on_every_coin(self):
        sk = make_skill("t_sk2", coins=4, power=0, damage=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("sinking", potency=2, count=4)
        b = make_battle([a], [e], all_heads(), log=True)
        attack(b, a, e, sk)
        self.assertEqual(e.sp, -8)
        self.assertEqual(len([x for x in b.state.log if x.get("kind") == "sp"]), 4)

    def test_sinking_can_be_disabled(self):
        """消融 F：关闭沉沦触发。"""
        sk = make_skill("t_sk3", coins=3, power=0, damage=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("sinking", potency=3, count=2)
        b = make_battle([a], [e], all_heads(sinking_enabled=False))
        attack(b, a, e, sk)
        self.assertEqual(e.sp, 0)

    def test_sinking_potency_accumulates(self):
        """沉沦强度会累积（这是「重投 E.G.O」的触发条件）。"""
        sk = make_skill("t_sk4", coins=2, power=0, damage=1, coin_effects=[
            {"when": "on_hit", "kind": "add_status", "key": "sinking",
             "potency": 2, "count": 1, "target": "other"}])
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.status_potency("sinking"), 4)


class TestButterflyStatus(unittest.TestCase):
    def test_butterfly_deals_sp_and_hp_damage(self):
        sk = make_skill("t_bf1", coins=1, power=0, damage=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("butterfly", potency=2, count=3)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.sp, -2)
        self.assertEqual(e.hp, 999 - 1 - 2)   # 硬币 1 + 蝶 2
        self.assertEqual(e.status_count("butterfly"), 2)

    def test_butterfly_special_can_be_disabled(self):
        """消融 G：只保留普通伤害。"""
        sk = make_skill("t_bf2", coins=1, power=0, damage=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("butterfly", potency=2, count=3)
        b = make_battle([a], [e], all_heads(butterfly_special_sinking=False))
        attack(b, a, e, sk)
        self.assertEqual(e.sp, 0)
        self.assertEqual(e.hp, 999 - 1)


class TestOtherStatuses(unittest.TestCase):
    def test_rupture(self):
        sk = make_skill("t_rp1", coins=2, power=0, damage=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("rupture", potency=5, count=1)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 2 - 5)  # 两次硬币伤害 + 一次破裂

    def test_bleed_triggers_on_skill_use(self):
        sk = make_skill("t_bl1", coins=1, power=0, damage=1)
        a = make_unit("a", Side.ALLY, hp=100)
        e = make_unit("e", Side.ENEMY, hp=999)
        a.add_status("bleed", potency=7, count=2)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(a.hp, 100 - 7)
        self.assertEqual(a.status_count("bleed"), 1)

    def test_burn_at_turn_end(self):
        a = make_unit("a", Side.ALLY, hp=100)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("burn", potency=9, count=3)
        b = make_battle([a], [e], all_heads())
        b.state.turn = 1
        b.end_turn()
        self.assertEqual(e.hp, 999 - 9)
        self.assertEqual(e.status_count("burn"), 2)

    def test_manor_echo_drains_sp_at_turn_end(self):
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999, sp=0)
        e.add_status("manor_echo", count=3)
        b = make_battle([a], [e], all_heads())
        b.state.turn = 1
        b.end_turn()
        self.assertEqual(e.sp, -6)

    def test_status_decay_at_turn_end(self):
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("timegap", count=3)
        b = make_battle([a], [e], all_heads())
        b.state.turn = 1
        b.end_turn()
        self.assertEqual(e.status_count("timegap"), 2)

    def test_fragile_increases_damage_taken(self):
        sk = make_skill("t_fr1", coins=1, power=0, damage=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("fragile", count=3)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        # 10 × (1 + 0.05×3) = 11.5 -> round() 取偶 -> 12
        self.assertEqual(e.hp, 999 - 12)


if __name__ == "__main__":
    unittest.main()
