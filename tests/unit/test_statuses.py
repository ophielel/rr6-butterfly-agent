"""状态语义验证 —— 按 wiki.gg/Sinking 等页面重写（docs/audit_report.md §3）。"""

from __future__ import annotations

import unittest

from helpers import all_heads, attack, make_battle, make_skill, make_unit
from rr6sim.core.config import SimConfig
from rr6sim.core.enums import Side, Sin


class TestSinking(unittest.TestCase):
    def test_sp_damage_and_count_consumption(self):
        """有 SP 单位：命中时失去等强度的 SP，层数 -1。"""
        sk = make_skill("t_sk1", coins=3, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999, sp=0)
        e.add_status("sinking", potency=3, count=2)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.sp, -6)              # 2 次触发 × 强度 3
        self.assertEqual(e.status_count("sinking"), 0)

    def test_sp_damage_only_when_has_sanity(self):
        sk = make_skill("t_sk2", coins=3, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999, sp=0)
        e.add_status("sinking", potency=3, count=2)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.sp, -6)
        self.assertEqual(b.counters.get("sinking_gloom_damage", 0), 0)

    def test_no_sanity_unit_takes_gloom_damage_instead(self):
        """无 SP 单位（Abnormality）：改为受到等强度的 Gloom 伤害（忽略物理抗性）。"""
        sk = make_skill("t_sk3", coins=2, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.has_sanity = False
        e.add_status("sinking", potency=5, count=2)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        # 2 枚硬币 → 2 次触发，每次 5 点 Gloom 固定伤害；另有 2 点硬币伤害
        self.assertEqual(e.hp, 999 - 2 - 10)
        self.assertEqual(e.sp, 0)
        self.assertEqual(b.counters.get("sinking_gloom_damage"), 10)

    def test_gloom_resistance_applies_to_sinking_damage(self):
        sk = make_skill("t_sk4", coins=1, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.has_sanity = False
        e.sin_resistances[Sin.GLOOM] = 0.5      # Ineff. → -25%
        e.add_status("sinking", potency=8, count=1)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(b.counters.get("sinking_gloom_damage"), 6)   # 8 × 0.75

    def test_sinking_can_be_disabled(self):
        sk = make_skill("t_sk5", coins=2, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.has_sanity = False
        e.add_status("sinking", potency=5, count=2)
        b = make_battle([a], [e], all_heads(sinking_vs_no_sp_deals_gloom_damage=False))
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 2)
        self.assertEqual(b.counters.get("sinking_gloom_damage", 0), 0)

    def test_potency_accumulates(self):
        """沉沦强度会累积（这是蝶与多段命中的收益来源）。"""
        sk = make_skill("t_sk6", coins=2, power=0, damage=0, base_power=1, coin_effects=[
            {"when": "on_hit", "kind": "add_status", "key": "sinking",
             "potency": 2, "count": 1, "target": "other"}])
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999, sp=0)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.status_potency("sinking"), 4)


class TestButterfly(unittest.TestCase):
    """蝶：Potency = The Living，Count = The Departed。"""

    def test_attacker_heals_sp(self):
        """命中时攻击者回复 (The Living / 4) SP（最少 1）。"""
        sk = make_skill("t_bf1", coins=1, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY, sp=0)
        e = make_unit("e", Side.ENEMY, hp=999, sp=0)
        e.add_status("butterfly", potency=8, count=1)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(a.sp, 2)   # 8 // 4

    def test_gloom_burst_when_owner_sp_negative(self):
        """自身 SP < 0 时：每个 Departed 造成 (Sinking Potency / 5) Gloom 伤害（上限 30）。"""
        sk = make_skill("t_bf2", coins=1, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY, sp=0)
        e = make_unit("e", Side.ENEMY, hp=999, sp=-10)
        e.add_status("butterfly", potency=4, count=2)     # Living 4 / Departed 2
        e.add_status("sinking", potency=10, count=5)      # 10 // 5 = 2
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        # 硬币 1 + Gloom 爆发 (2 × 2 = 4)
        self.assertEqual(e.hp, 999 - 1 - 4)
        self.assertEqual(b.counters.get("butterfly_gloom_damage"), 4)

    def test_gloom_burst_capped_at_30(self):
        sk = make_skill("t_bf3", coins=1, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY, sp=0)
        e = make_unit("e", Side.ENEMY, hp=999, sp=-10)
        e.add_status("butterfly", potency=15, count=15)
        e.add_status("sinking", potency=99, count=99)     # 99 // 5 = 19 → 19 × 15 = 285 → cap 30
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(b.counters.get("butterfly_gloom_damage"), 30)

    def test_no_burst_when_sp_not_negative(self):
        sk = make_skill("t_bf4", coins=1, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY, sp=0)
        e = make_unit("e", Side.ENEMY, hp=999, sp=0)
        e.add_status("butterfly", potency=8, count=4)
        e.add_status("sinking", potency=20, count=5)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(b.counters.get("butterfly_gloom_damage", 0), 0)

    def test_turn_end_converts_living_to_departed(self):
        """回合结束：Departed 归 0 → 获得等同 Living 的 Sinking → Living 转为 Departed。"""
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("butterfly", potency=4, count=2)
        b = make_battle([a], [e], all_heads())
        b.state.turn = 1
        b.end_turn()
        st = e.statuses.get("butterfly")
        self.assertEqual(st.potency, 0)
        self.assertEqual(st.count, 4)                 # Living 转为 Departed
        self.assertEqual(e.status_potency("sinking"), 4)


class TestOtherStatuses(unittest.TestCase):
    def test_fragile_is_additive_dynamic_modifier(self):
        """脆弱：每层 +10% 动态修正（wiki: 2 层 = +20%）。"""
        sk = make_skill("t_fr1", coins=1, power=0, damage=0, base_power=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("fragile", count=2)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 12)

    def test_fragile_and_weak_resistance_multiply(self):
        """脆弱（动态）与弱点抗性（静态）是相乘关系（wiki 的例子：1.2 × 1.2 = 1.44）。"""
        sk = make_skill("t_fr2", coins=1, power=0, damage=0, base_power=10, damage_type="slash")
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        from rr6sim.core.enums import DamageType
        e.resistances[DamageType.SLASH] = 1.5
        e.add_status("fragile", count=2)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - int(10 * 1.5 * 1.2))

    def test_rupture_is_flat_damage(self):
        sk = make_skill("t_rp1", coins=2, power=0, damage=0, base_power=1)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999)
        e.add_status("rupture", potency=5, count=1)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 999 - 2 - 5)

    def test_bleed_triggers_on_skill_use(self):
        sk = make_skill("t_bl1", coins=1, power=0, damage=0, base_power=1)
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

    def test_manor_echo_decays_but_has_no_direct_damage(self):
        """山庄的回响：真实规则是 50% 追加 Sinking Count + Panic 类型（未实现），不做直接伤害。"""
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=999, sp=0)
        e.add_status("manor_echo", count=3)
        b = make_battle([a], [e], all_heads())
        b.state.turn = 1
        b.end_turn()
        self.assertEqual(e.sp, 0)
        self.assertEqual(e.status_count("manor_echo"), 2)   # 回合结束 -1

    def test_shield_absorbs_damage_first(self):
        sk = make_skill("t_sh1", coins=1, power=0, damage=0, base_power=10)
        a = make_unit("a", Side.ALLY)
        e = make_unit("e", Side.ENEMY, hp=100, shield=333)
        b = make_battle([a], [e], all_heads())
        attack(b, a, e, sk)
        self.assertEqual(e.hp, 100)
        self.assertEqual(e.shield, 323)


if __name__ == "__main__":
    unittest.main()
