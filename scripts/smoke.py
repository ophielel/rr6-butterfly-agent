"""冒烟测试：跑一局贪心，打印关键统计，用于快速发现引擎/数据问题。

用法： python3 scripts/smoke.py [seed] [--deterministic] [--max-turns N]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from rr6sim.content.loader import Content  # noqa: E402
from rr6sim.core.config import SimConfig  # noqa: E402
from rr6sim.replay import format_replay_text  # noqa: E402
from rr6sim.search.greedy import run_greedy  # noqa: E402


def main() -> None:
    seed = 0
    deterministic = "--deterministic" in sys.argv
    max_turns = 15
    for i, a in enumerate(sys.argv):
        if a.isdigit():
            seed = int(a)
        if a == "--max-turns":
            max_turns = int(sys.argv[i + 1])
    cfg = SimConfig(deterministic=deterministic, max_turns=max_turns)
    content = Content()
    res = run_greedy(content, cfg, seed=seed)
    print(f"seed={seed} deterministic={deterministic} -> outcome={res['outcome']} "
          f"turns={res['turns']} boss_hp={res['boss_hp']} kill_turn={res['kill_turn']}")
    print("counters:", res["counters"])
    if "--replay" in sys.argv:
        from rr6sim.replay import export_replay

        print(format_replay_text(export_replay(res["battle"])))


if __name__ == "__main__":
    main()
