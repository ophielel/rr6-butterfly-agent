"""Golden replay 对比（计划书 §18.2）：模拟器必须逐事件复现固定脚本。"""

from __future__ import annotations

import json
import os
import unittest

from rr6sim.verify import event_digest

from .make_golden import GOLDEN_PATH, build_golden


class TestGoldenLine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(GOLDEN_PATH):
            raise unittest.SkipTest(f"缺少 golden 文件：{GOLDEN_PATH}")
        with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
            cls.golden = json.load(f)
        cls.actual = build_golden()

    def test_config_hash(self):
        self.assertEqual(self.actual["config_hash"], self.golden["config_hash"])

    def test_event_digest_matches(self):
        self.assertEqual(self.actual["digest"], self.golden["digest"],
                         "事件流与 golden 不一致：请检查是否改动了结算时点/倍率")

    def test_final_state_hash_matches(self):
        self.assertEqual(self.actual["final_state_hash"], self.golden["final_state_hash"])

    def test_outcome_matches(self):
        self.assertEqual(self.actual["outcome"], self.golden["outcome"])
        self.assertEqual(self.actual["turns"], self.golden["turns"])

    def test_key_counters_match(self):
        for key in ("repeat_coin", "sinking_sp_damage", "ego_use", "form_switch",
                    "clash_count", "phantom_stack_decay"):
            self.assertEqual(self.actual["counters"].get(key, 0),
                             self.golden["counters"].get(key, 0), f"counter {key} 不一致")

    def test_digest_is_stable_across_runs(self):
        self.assertEqual(event_digest([]), event_digest([]))
        self.assertEqual(build_golden()["digest"], self.actual["digest"])


if __name__ == "__main__":
    unittest.main()
