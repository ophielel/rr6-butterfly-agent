"""罗生蝶::Imago 机制验证 —— 按 wiki.gg 的 ABPage / passive 原文重写。"""

from __future__ import annotations

import unittest

from helpers import CONTENT, make_unit
from rr6sim.core.config import SimConfig
from rr6sim.core.enums import Side
from rr6sim.core.engine import Battle
from rr6sim.core.state import BattleState
from rr6sim.core.status import IN_THE_FUTURE, IN_THE_PAST, IN_THE_PRESENT


def imago_battle(**cfg_kw):
    cfg = SimConfig(boss_hp_scale=1.0, **cfg_kw).normalized()
    allies, enemies = CONTENT.make_encounter(cfg)
    st = BattleState(allies=allies, enemies=enemies, config=cfg, seed=0, rng_state=0)
    b = Battle(st, CONTENT)
    b.log_enabled = True
    return b, {u.uid: u for u in allies}, {u.uid: u for u in enemies}


class TestImagoStats(unittest.TestCase):
    def test_hp_formula(self):
        """hp = base + hpgrowth × level = 9090 + 275.44 × 60 = 25616。"""
        b, _, enemies = imago_battle()
        self.assertEqual(enemies["boss"].hp, 25616)

    def test_stagger_thresholds_are_percent_of_max_hp(self):
        b, _, enemies = imago_battle()
        boss = enemies["boss"]
        expected = [int(25616 * p) for p in (0.85, 0.65, 0.40, 0.10)]
        self.assertEqual(boss.stagger_thresholds, expected)

    def test_resistances(self):
        b, _, enemies = imago_battle()
        boss = enemies["boss"]
        from rr6sim.core.enums import Sin
        self.assertAlmostEqual(boss.resistance_value(Sin.WRATH), 1.25)
        self.assertAlmostEqual(boss.resistance_value(Sin.SLOTH), 0.75)

    def test_boss_has_no_sanity(self):
        b, _, enemies = imago_battle()
        self.assertFalse(enemies["boss"].has_sanity)

    def test_speed_range(self):
        b, _, enemies = imago_battle()
        self.assertEqual(enemies["boss"].speed_range, (1, 3))


class TestTimeStates(unittest.TestCase):
    def test_initial_stacks(self):
        b, _, enemies = imago_battle()
        boss = enemies["boss"]
        for key in (IN_THE_PAST, IN_THE_PRESENT, IN_THE_FUTURE):
            self.assertEqual(boss.status_count(key), 10)

    def test_active_state_is_highest_stack(self):
        b, _, enemies = imago_battle()
        boss = enemies["boss"]
        boss.state["active_time_state"] = IN_THE_PAST
        boss.set_status(IN_THE_PRESENT, 0, 15)
        b.activate_time_state()
        self.assertEqual(boss.state["active_time_state"], IN_THE_PRESENT)
        self.assertGreater(b.counters.get("time_state_changes", 0), 0)

    def test_tie_keeps_current_state(self):
        """并列最高时保持当前激活状态（wiki: the currently active state does not change）。"""
        b, _, enemies = imago_battle()
        boss = enemies["boss"]
        boss.state["active_time_state"] = IN_THE_FUTURE
        for key in (IN_THE_PAST, IN_THE_PRESENT, IN_THE_FUTURE):
            boss.set_status(key, 0, 10)
        b.activate_time_state()
        self.assertEqual(boss.state["active_time_state"], IN_THE_FUTURE)

    def test_skill_rotation_depends_on_state_and_hp(self):
        b, _, enemies = imago_battle()
        boss = enemies["boss"]
        boss.state["active_time_state"] = IN_THE_PAST
        boss.state["cycle_turn"] = 0
        first = b._rotation_skill(boss, boss.slots[0])
        self.assertEqual(first, "im_temper_and_cast")
        boss.state["active_time_state"] = IN_THE_FUTURE
        self.assertEqual(b._rotation_skill(boss, boss.slots[0]), "im_corrosive_disintegration")
        boss.state["active_time_state"] = IN_THE_PRESENT
        self.assertEqual(b._rotation_skill(boss, boss.slots[0]), "im_anitya")


class TestIllusoryButterflies(unittest.TestCase):
    def test_section5_wave_has_boss_and_three_illusions(self):
        b, _, enemies = imago_battle()
        self.assertEqual(len(b.state.phantoms()), 3)
        time_types = {p.time_type for p in b.state.phantoms()}
        self.assertEqual(time_types, {IN_THE_PAST, IN_THE_PRESENT, IN_THE_FUTURE})

    def test_illusions_start_with_shield(self):
        b, _, enemies = imago_battle()
        for p in b.state.phantoms():
            self.assertEqual(p.shield, 333)

    def test_hitting_illusion_removes_matching_stack(self):
        """Moment of Entangled Lives：幻影被作为主要目标攻击时，本体失去对应栈。"""
        b, allies, enemies = imago_battle(coin_mode="always_heads")
        boss = enemies["boss"]
        past = enemies["phantom_past"]
        dummy = list(allies.values())[0]
        before = boss.status_count(IN_THE_PAST)
        from helpers import make_skill

        sk = make_skill("t_il1", coins=3, power=0, damage=0, base_power=5)
        b.attack_with(dummy, sk, past)
        self.assertEqual(boss.status_count(IN_THE_PAST), before - 3)
        self.assertEqual(boss.status_count(IN_THE_PRESENT), 10)

    def test_only_matching_illusion_affects_its_stack(self):
        b, allies, enemies = imago_battle(coin_mode="always_heads")
        boss = enemies["boss"]
        future = enemies["phantom_future"]
        dummy = list(allies.values())[0]
        from helpers import make_skill

        sk = make_skill("t_il2", coins=2, power=0, damage=0, base_power=5)
        b.attack_with(dummy, sk, future)
        self.assertEqual(boss.status_count(IN_THE_FUTURE), 8)
        self.assertEqual(boss.status_count(IN_THE_PAST), 10)

    def test_shield_absorbs_illusion_damage(self):
        b, allies, enemies = imago_battle(coin_mode="always_heads")
        past = enemies["phantom_past"]
        dummy = list(allies.values())[0]
        from helpers import make_skill

        sk = make_skill("t_il3", coins=1, power=0, damage=0, base_power=50)
        dummy.offense_level = 60          # 与幻影同级，排除等级修正
        b.attack_with(dummy, sk, past)
        self.assertEqual(past.shield, 333 - 50)
        self.assertEqual(past.hp, 1)
        self.assertFalse(past.alive is False)


class TestBossEndToEndSinking(unittest.TestCase):
    def test_sinking_deals_gloom_damage_to_boss(self):
        """无 SP 的 Abnormality：沉沦改为直接 Gloom 伤害（本实验的核心收益）。"""
        b, allies, enemies = imago_battle(coin_mode="always_heads")
        boss = enemies["boss"]
        boss.set_status("sinking", potency=20, count=10)
        dummy = list(allies.values())[0]
        from helpers import make_skill

        sk = make_skill("t_e2e", coins=4, power=0, damage=0, base_power=5)
        hp_before = boss.hp
        b.attack_with(dummy, sk, boss)
        # 4 枚硬币 → 4 次 × 20 = 80 点 Gloom 固定伤害（Gloom 抗性 1.0）
        self.assertEqual(b.counters.get("sinking_gloom_damage"), 80)
        # 另有 4 × 6 点硬币伤害（Wrath 5 威力 × 1.25 抗性，等级同为 60 → 无等级修正）
        self.assertEqual(hp_before - boss.hp, 80 + 24)


if __name__ == "__main__":
    unittest.main()
