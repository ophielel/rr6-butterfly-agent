"""基准对比：Greedy vs 手写「沉沦 -> 重投 E.G.O」轴，以及各项消融。

用法：
    python3 scripts/benchmark.py --seeds 5 --scale 0.5
"""

from __future__ import annotations

import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from rr6sim.content.loader import Content  # noqa: E402
from rr6sim.core.config import SimConfig  # noqa: E402
from rr6sim.search.greedy import run_greedy  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manual_line import run_line  # noqa: E402


def _arg(name: str, default):
    if name in sys.argv:
        return type(default)(sys.argv[sys.argv.index(name) + 1])
    return default


def summarize(name: str, results: list) -> None:
    kills = [r["kill_turn"] for r in results if r["kill_turn"]]
    wins = sum(1 for r in results if r["outcome"] == "ally_win")
    boss_left = [r["boss_hp"] for r in results if r["outcome"] != "ally_win"]
    med = statistics.median(kills) if kills else None
    print(f"{name:<26} 胜率 {wins}/{len(results)}  击杀回合 中位={med} "
          f"min={min(kills) if kills else '-'} max={max(kills) if kills else '-'} "
          f"未击杀时剩余HP均值={statistics.mean(boss_left) if boss_left else '-'}")


def main() -> None:
    seeds = _arg("--seeds", 5)
    scale = _arg("--scale", 0.5)
    max_turns = _arg("--max-turns", 20)
    content = Content()

    def cfg(**kw):
        base = dict(max_turns=max_turns, boss_hp_scale=scale)
        base.update(kw)
        return SimConfig(**base)

    variants = {
        "Greedy 基线": cfg(),
        "手写轴(完整)": cfg(),
        "A1 禁用蝶箱庄严哀悼": cfg(disabled_egos=["solemn_lament_yisang"]),
        "A2 禁用目灯虫庄严哀悼": cfg(disabled_egos=["solemn_lament_gregor"]),
        "A3 禁用辛克莱和声": cfg(disabled_egos=["harmony_sinclair"]),
        "E 关闭重复硬币": cfg(repeat_coin_enabled=False),
        "F 关闭沉沦触发": cfg(sinking_enabled=False),
        "G 关闭蝶特殊沉沦": cfg(butterfly_special_sinking=False),
    }
    for name, c in variants.items():
        results = []
        for seed in range(seeds):
            if name.startswith("Greedy"):
                results.append(run_greedy(content, c, seed=seed))
            else:
                results.append(run_line(content, c, seed=seed))
        summarize(name, results)


if __name__ == "__main__":
    main()
