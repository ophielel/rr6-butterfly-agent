"""环境 API 演示 / replay 导出：

    python3 scripts/run_env.py --seed 1 --config configs/rr6_butterfly_base.yaml
    python3 scripts/run_env.py --seed 1 --out runs/demo_seed1.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from rr6sim.config_io import load_config  # noqa: E402
from rr6sim.env.rr6_env import RR6ButterflyEnv  # noqa: E402
from rr6sim.replay import format_replay_text, save_replay  # noqa: E402
from rr6sim.search.greedy import greedy_plan  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--config", type=str, default="")
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--laws", action="store_true", help="打印第 1 回合的合法动作")
    ap.add_argument("--text", action="store_true", help="打印人类可读 replay")
    args = ap.parse_args()

    cfg = load_config(args.config) if args.config else None
    env = RR6ButterflyEnv(cfg, seed=args.seed)
    obs = env.reset(seed=args.seed)
    print(f"observation_size={len(obs)}  legal_actions={len(env.legal_actions())}")
    if args.laws:
        print("-- 第 1 个行动槽的合法「行动」 --")
        for i, a in enumerate(env.legal_actions()):
            print(f"  [{i}] {a['label']}")
        print("-- 选定第 0 个行动后，可选的「目标」 --")
        first = env.legal_actions()[0]
        probe = RR6ButterflyEnv(cfg, seed=args.seed)
        probe.reset(seed=args.seed)
        probe.battle.assign_action(probe._slot, first["kind"], first["id"], first.get("corrosion", False))
        probe._phase = "target"
        for i, t in enumerate(probe.legal_actions()):
            print(f"  [{i}] {t['label']}")
    reward = 0.0
    while True:
        plan = greedy_plan(env.battle)
        obs, r, term, trunc, info = env.step_plan(plan)
        reward += r
        print(f"T{info['turn']}: reward={r:+.1f} total={reward:+.1f} "
              f"boss_hp={info['summary']['boss_hp']} form={info['summary']['form']} "
              f"sinking={info['summary']['sinking']} repeat={info['counters'].get('repeat_coin', 0)}")
        if term or trunc:
            print(f"terminal={info['outcome']} {info['terminal']}")
            break
    replay = env.export_replay()
    if args.text:
        print(format_replay_text(replay))
    if args.out:
        save_replay(replay, args.out)
        print(f"replay 已写入 {args.out}")
    else:
        print("stats:", json.dumps(replay["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
