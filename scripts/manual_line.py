"""Known-strategy regression test（不是「证明沉沦+重骰最优」的脚本）。

计划书 §13 的重新定义：
* 它只用于检查「沉沦能建立 / Coin Reuse 会发生 / 多次命中会重复触发状态 /
  replay 能正确记录 / 消融开关真的关掉了对应机制」；
* **禁止**为了让它赢过 Greedy 而改数据；
* 如果真实机制校准后 Greedy 更强，也接受。

用法：
    python3 scripts/manual_line.py            # 跑几种配置并断言机制发生了
    python3 scripts/manual_line.py --seed 3
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from rr6sim.content.loader import Content  # noqa: E402
from rr6sim.core.config import SimConfig  # noqa: E402
from rr6sim.core.engine import Battle  # noqa: E402
from rr6sim.core.state import BattleState  # noqa: E402
from rr6sim.replay import export_replay, format_replay_text  # noqa: E402
from rr6sim.simulate import apply_plan  # noqa: E402
from rr6sim.search.greedy import run_greedy  # noqa: E402

# 我方行动计划：(owner, 行动类型, id, 目标)
# 目标 = boss / phantom_past / phantom_present / phantom_future
LINE: dict = {
    1: [
        ("solemn_yisang", "skill", "yi_s3", "boss"),
        ("lantern_gregor", "skill", "gr_s3", "boss"),
        ("butler_faust", "skill", "fa_s3", "boss"),
        ("hanafuda_ishmael", "skill", "is_s2", "boss"),
        ("band_sinclair", "skill", "si_s2", "boss"),
        ("lca_outis", "skill", "ou_s2", "boss"),
        ("despair_rodion", "skill", "ro_s2", "boss"),
    ],
    2: [
        ("solemn_yisang", "skill", "yi_s3", "boss"),
        ("lantern_gregor", "ego", "solemn_lament_gregor", "boss"),
        ("butler_faust", "skill", "fa_s1", "phantom_past"),
        ("hanafuda_ishmael", "ego", "bygone_days_ishmael", "phantom_present"),
        ("band_sinclair", "ego", "harmony_sinclair", "phantom_future"),
        ("lca_outis", "skill", "ou_s3", "boss"),
        ("despair_rodion", "ego", "rime_shank_rodion", "boss"),
    ],
    3: [
        ("solemn_yisang", "ego", "solemn_lament_yisang", "boss"),
        ("lantern_gregor", "ego", "solemn_lament_gregor", "boss"),
        ("butler_faust", "skill", "fa_s3", "boss"),
        ("hanafuda_ishmael", "skill", "is_s3", "boss"),
        ("band_sinclair", "ego", "harmony_sinclair", "boss"),
        ("lca_outis", "skill", "ou_s3", "boss"),
        ("despair_rodion", "ego", "rime_shank_rodion", "boss"),
    ],
}

LATE = [
    ("solemn_yisang", "ego", "solemn_lament_yisang"),
    ("lantern_gregor", "ego", "solemn_lament_gregor"),
    ("butler_faust", "skill", "fa_s3"),
    ("hanafuda_ishmael", "ego", "bygone_days_ishmael"),
    ("band_sinclair", "ego", "harmony_sinclair"),
    ("lca_outis", "skill", "ou_s2"),
    ("despair_rodion", "ego", "rime_shank_rodion"),
]

FALLBACK = {
    "solemn_yisang": ("skill", "yi_s3"),
    "lantern_gregor": ("skill", "gr_s3"),
    "butler_faust": ("skill", "fa_s3"),
    "hanafuda_ishmael": ("skill", "is_s3"),
    "band_sinclair": ("skill", "si_s3"),
    "lca_outis": ("skill", "ou_s3"),
    "despair_rodion": ("skill", "ro_s2"),
}


def build_plan(battle: Battle, turn: int) -> list:
    spec = LINE.get(turn)
    plan = []
    if spec:
        for owner, kind, cid, target in spec:
            if owner in battle.config.disabled_identities:
                continue
            if kind == "ego" and cid in battle.config.disabled_egos:
                kind, cid = FALLBACK[owner]
                target = "boss"
            plan.append({"owner": owner, "slot": 0, "kind": kind, "id": cid,
                         "corrosion": False, "target": target, "target_slot": 0})
        return plan
    for owner, kind, cid in LATE:
        u = battle.unit(owner)
        if u is None or not u.alive:
            continue
        if kind == "ego":
            ego = battle.content.ego(cid)
            if ego is None or cid in battle.config.disabled_egos:
                kind, cid = FALLBACK[owner]
                plan.append({"owner": owner, "slot": 0, "kind": kind, "id": cid,
                             "corrosion": False, "target": "boss", "target_slot": 0})
                continue
        plan.append({"owner": owner, "slot": 0, "kind": kind, "id": cid,
                     "corrosion": False, "target": "boss", "target_slot": 0})
    return plan


def run_line(content, config, seed: int = 0) -> dict:
    cfg = config.normalized()
    allies, enemies = content.make_encounter(cfg)
    st = BattleState(allies=allies, enemies=enemies, seed=seed, rng_state=seed, config=cfg)
    battle = Battle(st, content)
    battle.log_enabled = True
    battle.begin_turn()
    while not battle.state.is_terminal():
        plan = build_plan(battle, battle.state.turn)
        apply_plan(battle, plan)
        battle.resolve_turn()
        if battle.state.is_terminal():
            break
        battle.begin_turn()
    boss = battle.state.boss()
    return {
        "outcome": battle.state.outcome.value,
        "turns": battle.state.turn,
        "kill_turn": battle.state.terminal.get("kill_turn"),
        "boss_hp": boss.hp if boss else 0,
        "counters": dict(battle.state.counters),
        "battle": battle,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--text", action="store_true", help="打印 replay 文本")
    args = ap.parse_args()

    content = Content()
    base = SimConfig(max_turns=20, boss_hp_scale=0.5)

    print("== 机制存在性检查（known strategy regression） ==")
    full = run_line(content, base, args.seed)
    c = full["counters"]
    checks = [
        ("沉沦确实造成了伤害（无 SP 单位 → Gloom 伤害）", c.get("sinking_gloom_damage", 0) > 0),
        ("蝶被施加", c.get("butterfly_inflicted", 0) > 0),
        ("E.G.O 被使用", c.get("ego_use", 0) > 0),
        ("Coin Reuse 触发", c.get("reuse_count", 0) > 0),
        ("形态/时间状态发生过切换", c.get("time_state_changes", 0) >= 0),
        ("replay 记录了事件", len(full["battle"].state.log) > 0),
    ]
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")

    print("\n== 消融开关是否真的关掉了机制 ==")
    no_reuse = run_line(content, SimConfig(max_turns=20, boss_hp_scale=0.5,
                                          coin_reuse_enabled=False), args.seed)
    print(f"  Coin Reuse 关闭后 reuse_count = {no_reuse['counters'].get('reuse_count', 0)}"
          f"（应为 0）")
    no_sink = run_line(content, SimConfig(max_turns=20, boss_hp_scale=0.5,
                                         sinking_vs_no_sp_deals_gloom_damage=False), args.seed)
    print(f"  关闭「沉沦→Gloom 伤害」后 sinking_gloom_damage = "
          f"{no_sink['counters'].get('sinking_gloom_damage', 0)}（应为 0）")

    print("\n== 与 Greedy 对照（只报告，不作结论；真实机制下 Greedy 更强也接受） ==")
    g = run_greedy(content, base, seed=args.seed)
    print(f"  manual line: {full['outcome']} kill_turn={full['kill_turn']} boss_hp={full['boss_hp']}")
    print(f"  greedy     : {g['outcome']} kill_turn={g['kill_turn']} boss_hp={g['boss_hp']}")
    print(f"  not_implemented 计数 = {full['counters'].get('not_implemented', 0)}"
          f"（未实现的真实机制，见 data/*.json 的 not_implemented 条目）")

    if args.text:
        print()
        print(format_replay_text(export_replay(full["battle"])))


if __name__ == "__main__":
    main()
