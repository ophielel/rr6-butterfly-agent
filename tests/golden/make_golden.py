"""生成 golden replay 基线（计划书 §18.2）。

运行：
    PYTHONPATH=src:tests python3 tests/golden/make_golden.py

任何会改变结算结果（伤害/状态时点/拼点/幻影机制）的改动都会让
``test_golden_replay.py`` 失败，从而强制我们显式确认这次改动。
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from manual_line import run_line  # noqa: E402
from rr6sim.content.loader import Content  # noqa: E402
from rr6sim.core.config import SimConfig  # noqa: E402
from rr6sim.verify import event_digest  # noqa: E402

GOLDEN_PATH = os.path.join(HERE, "golden_line_seed0.json")

#: 固定硬币脚本：不依赖精神力，完全可复现（Stage A 的确定性环境）
COIN_SCRIPT = [True, False, True, True, False, True, False, True,
               False, False, True, True, True, False, True, False]


def golden_config() -> SimConfig:
    return SimConfig(
        coin_mode="script",
        coin_script=COIN_SCRIPT,
        speed_mode="fixed",
        skill_draw_mode="fixed",
        boss_ai="script",
        max_turns=20,
        boss_hp_scale=0.5,
    ).normalized()


def build_golden() -> dict:
    content = Content()
    res = run_line(content, golden_config(), seed=0)
    battle = res["battle"]
    return {
        "_note": "golden replay：手写「沉沦 -> 重投 E.G.O」轴在固定硬币脚本下的完整结算摘要。"
                 "更新方式：PYTHONPATH=src:tests python3 tests/golden/make_golden.py",
        "config": golden_config().to_dict(),
        "config_hash": golden_config().hash(),
        "seed": 0,
        "outcome": battle.state.outcome.value,
        "turns": battle.state.turn,
        "terminal": dict(battle.state.terminal),
        "counters": dict(battle.state.counters),
        "digest": event_digest(battle.state.log),
        "final_state_hash": battle.state.hash(),
        "events": len(battle.state.log),
    }


def main() -> None:
    golden = build_golden()
    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        json.dump(golden, f, ensure_ascii=False, indent=1)
    print(f"写入 {GOLDEN_PATH}")
    print(json.dumps({k: v for k, v in golden.items() if k != "config"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
