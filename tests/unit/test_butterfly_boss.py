"""罗生蝶 Boss 机制验证（计划书 §18.1 的 Boss 相关条目）。"""

from __future__ import annotations

import unittest

from helpers import CONTENT, all_heads, attack, make_battle, make_skill, make_unit
from rr6sim.core.config import SimConfig
from rr6sim.core.enums import Side
from rr6sim.core.status import FUTURE, PAST, PRESENT


def boss_field(**cfg_kw):
    """构造「1 名我方 + 罗生蝶本体 + 三幻影」的测试战场。"""
    cfg = SimConfig(**cfg_kw).normalized()
    boss = CONTENT.make_enemy(CONTENT.boss_def, cfg, hp_override=6404)
    phantoms = [CONTENT.make_enemy(ph, cfg, hp_override=1000) for ph in CONTENT.phantom_defs]
    ally = make_unit("tester", Side.ALLY, hp=500, sp=30)
    b = make_battle([ally], [boss] + phantoms, cfg)
    for k in (PAST, PRESENT, FUTURE):
        boss.add_status(k, count=2)
    boss.state["form"] = "neutral"
    b.state.turn = 1
    return b, ally, boss, {p.uid: p for p in phantoms}


class TestPhantomStacks(unittest.TestCase):
    def test_each_coin_decays_matching_stack(self):
        """攻击幻影：每枚硬币只削减对应的状态栈 1 层。"""
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        sk = make_skill("t_ph1", coins=3, power=0, damage=10)
        attack(b, ally, ph["phantom_past"], sk)
        self.assertEqual(boss.status_count(PAST), 0)   # 2 -> 0（不会变负）
        self.assertEqual(boss.status_count(PRESENT), 2)
        self.assertEqual(boss.status_count(FUTURE), 2)

    def test_only_matching_phantom_decays(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        sk = make_skill("t_ph2", coins=2, power=0, damage=10)
        attack(b, ally, ph["phantom_future"], sk)
        self.assertEqual(boss.status_count(PAST), 2)
        self.assertEqual(boss.status_count(PRESENT), 2)
        self.assertEqual(boss.status_count(FUTURE), 0)

    def test_attacking_boss_does_not_decay_stacks(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        sk = make_skill("t_ph3", coins=3, power=0, damage=10)
        attack(b, ally, boss, sk)
        self.assertEqual([boss.status_count(k) for k in (PAST, PRESENT, FUTURE)], [2, 2, 2])

    def test_repeat_coin_decays_stack_again(self):
        """重复投掷属于新的硬币，会再削一层。"""
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        sk = make_skill("t_ph4", coins=2, power=0, damage=10, coin_effects=[
            {"when": "on_hit", "kind": "repeat_coin", "times": 1}])
        boss.set_status(PAST, 0, 10)
        attack(b, ally, ph["phantom_past"], sk)
        self.assertEqual(boss.status_count(PAST), 10 - 4)  # 2 枚硬币 × 2 次投掷

    def test_decay_can_be_disabled(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads", phantom_stack_decay_per_coin=0)
        sk = make_skill("t_ph5", coins=3, power=0, damage=10)
        attack(b, ally, ph["phantom_past"], sk)
        self.assertEqual(boss.status_count(PAST), 2)


class TestPhantomTransfer(unittest.TestCase):
    def test_damage_transfers_to_boss(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        sk = make_skill("t_tr1", coins=2, power=0, damage=10)
        before = boss.hp
        attack(b, ally, ph["phantom_present"], sk)
        self.assertEqual(ph["phantom_present"].hp, 1000 - 20)
        self.assertEqual(boss.hp, before - 20)

    def test_transfer_ratio(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads", phantom_damage_transfer=0.5)
        sk = make_skill("t_tr2", coins=2, power=0, damage=10)
        before = boss.hp
        attack(b, ally, ph["phantom_present"], sk)
        self.assertEqual(boss.hp, before - 10)


class TestPhantomRestore(unittest.TestCase):
    def test_untargeted_phantoms_restore(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        b.state.flags["targeted_phantoms"] = ["phantom_past"]
        b.end_turn()
        self.assertEqual(boss.status_count(PAST), 2)      # 被攻击，不回补
        self.assertEqual(boss.status_count(PRESENT), 4)   # +2
        self.assertEqual(boss.status_count(FUTURE), 4)

    def test_broken_phantom_does_not_restore(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        p = ph["phantom_present"]
        b.apply_damage(ally, p, 5000, None)
        self.assertFalse(p.alive)
        b.end_turn()
        self.assertEqual(boss.status_count(PRESENT), 2)

    def test_phantom_revives_after_configured_turns(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads", phantom_broken_turns=1)
        p = ph["phantom_present"]
        b.apply_damage(ally, p, 5000, None)
        self.assertFalse(p.alive)
        b.begin_turn()   # turn 2
        self.assertTrue(p.alive)
        self.assertEqual(p.hp, p.max_hp)


class TestFormAndThresholds(unittest.TestCase):
    def test_form_is_highest_stack(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        boss.set_status(PAST, 0, 2)
        boss.set_status(PRESENT, 0, 5)
        boss.set_status(FUTURE, 0, 1)
        b.change_form()
        self.assertEqual(boss.state["form"], "present")

    def test_form_switch_grants_timegap(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads", form_switch_timegap=2)
        boss.set_status(FUTURE, 0, 9)
        b.change_form()
        self.assertEqual(boss.state["form"], "future")
        self.assertEqual(boss.status_count("timegap"), 2)

    def test_no_timegap_when_form_unchanged(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads", form_switch_timegap=2)
        b.change_form()   # 三栈相同 -> 保持 neutral 之外的首个最大者
        first = boss.state["form"]
        gap = boss.status_count("timegap")
        b.change_form()
        self.assertEqual(boss.state["form"], first)
        self.assertEqual(boss.status_count("timegap"), gap)

    def test_hp_threshold_refills_stacks(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads", hp_threshold_stack_bonus=2)
        boss.state["stack_thresholds"] = [3000]
        boss.state["stack_threshold_index"] = 0
        boss.set_status(PAST, 0, 1)
        boss.set_status(PRESENT, 0, 1)
        boss.set_status(FUTURE, 0, 1)
        b.apply_damage(ally, boss, 4000, None)
        self.assertEqual([boss.status_count(k) for k in (PAST, PRESENT, FUTURE)], [3, 3, 3])
        self.assertEqual(boss.state["stack_threshold_index"], 1)

    def test_boss_stagger_thresholds(self):
        b, ally, boss, ph = boss_field(coin_mode="always_heads")
        # stagger 阈值按 HP 百分比缩放（0.9 / 0.7 / 0.47 / 0.23）
        self.assertEqual(boss.stagger_thresholds[0], int(6404 * 0.9))
        b.apply_damage(ally, boss, 6404 - int(6404 * 0.9), None)
        self.assertTrue(boss.staggered)
        self.assertEqual(boss.stagger_index, 1)


if __name__ == "__main__":
    unittest.main()
