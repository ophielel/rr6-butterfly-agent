"""合法目标选择回归测试（审计 §7）。

关键区分：
* 「这个敌方槽位会不会打出攻击」——由 `slot.cancelled / acted / staggered` 决定；
* 「这个单位能不能被打」——由 `alive / targetable`（部位是否被破坏）决定。

混淆两者会导致「Boss 被混乱后反而不可选中」这种致命 bug。
"""

from __future__ import annotations

import unittest

from helpers import CONTENT, make_unit
from rr6sim.core.config import SimConfig
from rr6sim.core.engine import Battle
from rr6sim.core.enums import Side
from rr6sim.core.state import BattleState


def field(**cfg_kw):
    cfg = SimConfig(**cfg_kw).normalized()
    allies, enemies = CONTENT.make_encounter(cfg)
    st = BattleState(allies=allies, enemies=enemies, config=cfg, seed=0, rng_state=0)
    b = Battle(st, CONTENT)
    b.log_enabled = True
    return b, allies[0], {u.uid: u for u in enemies}


def target_uids(battle, slot):
    return {t["uid"] for t in battle.legal_targets(slot)}


class TestLegalTargets(unittest.TestCase):
    def test_staggered_boss_is_still_targetable(self):
        b, ally, enemies = field()
        boss = enemies["boss"]
        b.force_stagger(boss)
        self.assertTrue(boss.staggered)
        self.assertIn("boss", target_uids(b, ally.slots[0]))
        # 混乱 → 不可能拼点，只能是单方面攻击
        for t in b.legal_targets(ally.slots[0]):
            if t["uid"] == "boss":
                self.assertFalse(t["clash"])

    def test_non_acting_phantom_is_still_targetable(self):
        """phantom_acts=false（幻影不行动）≠ 不能被攻击。"""
        b, ally, enemies = field(encounter_buffs={"phantom_acts": False})
        b.begin_turn()
        for p in b.state.phantoms():
            self.assertTrue(p.slots[0].cancelled)
        uids = target_uids(b, ally.slots[0])
        for p in b.state.phantoms():
            self.assertIn(p.uid, uids)

    def test_enemy_with_no_ai_is_still_targetable(self):
        """boss_ai=none（敌方完全不行动）时仍然可以被单方面攻击。"""
        b, ally, enemies = field(boss_ai="none")
        b.begin_turn()
        boss = enemies["boss"]
        self.assertTrue(all(s.cancelled for s in boss.slots))
        self.assertIn("boss", target_uids(b, ally.slots[0]))

    def test_dead_or_non_targetable_units_are_excluded(self):
        b, ally, enemies = field()
        boss = enemies["boss"]
        phantom = enemies["phantom_past"]
        boss.alive = False
        phantom.targetable = False
        uids = target_uids(b, ally.slots[0])
        self.assertNotIn("boss", uids)
        self.assertNotIn("phantom_past", uids)
        self.assertIn("phantom_present", uids)

    def test_clash_only_when_mutual(self):
        """只有「互相指定同一个槽位」才会拼点；否则是单方面攻击。"""
        b, ally, enemies = field(coin_mode="always_heads")
        b.begin_turn()
        boss = enemies["boss"]
        # 手动让 Boss 的槽位指向我方 slot 0
        boss.slots[0].choice_kind = boss.slots[0].choice_kind
        boss.slots[0].target_uid = ally.uid
        boss.slots[0].target_slot = 0
        boss.slots[0].cancelled = False
        boss.slots[0].acted = False
        entry = next(t for t in b.legal_targets(ally.slots[0]) if t["uid"] == "boss" and t["slot"] == 0)
        self.assertTrue(entry["clash"])


if __name__ == "__main__":
    unittest.main()
