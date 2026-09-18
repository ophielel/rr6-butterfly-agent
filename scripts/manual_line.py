"""手工输入「已知轴」验证（计划书 §24 最小成功版本第 2 条）。

思路：前两回合建立沉沦 / 亡蝶 / 山庄回响，第三回合起用多硬币 + 重复投掷 E.G.O 爆发。
如果模拟器正确，这条手写轴的击杀回合应该明显优于 Greedy；
一旦关闭「重复硬币」或「沉沦」，收益应该明显下降。

用法：
    python3 scripts/manual_line.py                 # 完整 / 关闭重投 / 关闭沉沦 三种对比
    python3 scripts/manual_line.py --replay 3      # 打印前 3 回合事件
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from rr6sim.content.loader import Content  # noqa: E402
from rr6sim.core.config import SimConfig  # noqa: E402
from rr6sim.core.enums import SlotKind  # noqa: E402
from rr6sim.core.engine import Battle  # noqa: E402
from rr6sim.core.state import BattleState  # noqa: E402
from rr6sim.replay import export_replay, format_replay_text  # noqa: E402

# 每条 = (owner, 行动类型, id, 目标 uid, 目标槽位)
# 前两回合：堆沉沦。第三回合起：庄严哀悼 / 和声 / 冰结之爪 爆发。
LINE: dict = {
    1: [
        ("solemn_yisang", "skill", "yi_s3", "boss", 0),
        ("lantern_gregor", "skill", "gr_s3", "boss", 0),
        ("butler_faust", "skill", "fa_s3", "boss", 0),
        ("hanafuda_ishmael", "skill", "is_s2", "boss", 0),
        ("band_sinclair", "skill", "si_s2", "boss", 0),
        ("lca_outis", "skill", "ou_s2", "boss", 0),
        ("despair_rodion", "skill", "ro_s2", "boss", 0),
    ],
    2: [
        ("solemn_yisang", "ego", "solemn_lament_yisang", "boss", 0),
        ("lantern_gregor", "skill", "gr_s3", "boss", 0),
        ("butler_faust", "skill", "fa_s1", "phantom_past", 0),
        ("hanafuda_ishmael", "skill", "is_s3", "phantom_present", 0),
        ("band_sinclair", "skill", "si_s3", "phantom_future", 0),
        ("lca_outis", "skill", "ou_s3", "boss", 0),
        ("despair_rodion", "ego", "frost_claw_rodion", "boss", 0),
    ],
    3: [
        ("solemn_yisang", "ego", "solemn_lament_yisang", "boss", 0),
        ("lantern_gregor", "ego", "solemn_lament_gregor", "boss", 0),
        ("butler_faust", "skill", "fa_s3", "boss", 0),
        ("hanafuda_ishmael", "ego", "yesteryear_ishmael", "boss", 0),
        ("band_sinclair", "ego", "harmony_sinclair", "boss", 0),
        ("lca_outis", "skill", "ou_s3", "boss", 0),
        ("despair_rodion", "ego", "frost_claw_rodion", "boss", 0),
    ],
}

# 第 4 回合以后：全 E.G.O 循环（SP 不够时自动退化为普通技能）
LATE: list = [
    ("solemn_yisang", "ego", "solemn_lament_yisang"),
    ("lantern_gregor", "ego", "solemn_lament_gregor"),
    ("butler_faust", "skill", "fa_s3"),
    ("hanafuda_ishmael", "ego", "yesteryear_ishmael"),
    ("band_sinclair", "skill", "si_s3"),
    ("lca_outis", "skill", "ou_s2"),
    ("despair_rodion", "ego", "frost_claw_rodion"),
]

# 兜底：SP 不够用 E.G.O 时改用的普通技能
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
    for entry in (spec or []):
        owner, kind, cid, target, tslot = entry
        if kind == "ego" and cid in battle.config.disabled_egos:
            kind, cid = FALLBACK[owner]
            target, tslot = "boss", 0
        plan.append({"owner": owner, "slot": 0, "kind": kind, "id": cid,
                     "corrosion": False, "target": target, "target_slot": tslot})
    if spec is None:
        for owner, kind, cid in LATE:
            u = battle.unit(owner)
            if u is None or not u.alive:
                continue
            if kind == "ego":
                ego = battle.content.ego(cid)
                if u.sp < ego.sp_cost or cid in battle.config.disabled_egos:
                    kind2, cid2 = FALLBACK[owner]
                    plan.append({"owner": owner, "slot": 0, "kind": kind2, "id": cid2,
                                 "corrosion": False, "target": "boss", "target_slot": 0})
                    continue
            plan.append({"owner": owner, "slot": 0, "kind": kind, "id": cid,
                         "corrosion": False, "target": "boss", "target_slot": 0})
    return plan


def run_line(content, config, seed: int = 0) -> dict:
    from rr6sim.simulate import apply_plan

    cfg = config.normalized()
    allies, enemies = content.make_encounter(cfg)
    st = BattleState(allies=allies, enemies=enemies, seed=seed, rng_state=seed, config=cfg)
    battle = Battle(st, content)
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
    content = Content()
    base = SimConfig(max_turns=20)
    variants = {
        "完整": base,
        "关闭重复硬币(E)": SimConfig(max_turns=20, repeat_coin_enabled=False),
        "关闭沉沦(F)": SimConfig(max_turns=20, sinking_enabled=False),
        "关闭蝶特殊沉沦(G)": SimConfig(max_turns=20, butterfly_special_sinking=False),
        "无E.G.O(D)": SimConfig(max_turns=20,
                                disabled_egos=["solemn_lament_yisang", "solemn_lament_gregor",
                                               "harmony_sinclair", "yesteryear_yisang",
                                               "yesteryear_ishmael", "frost_claw_rodion"]),
    }
    for name, cfg in variants.items():
        res = run_line(content, cfg, seed=int(sys.argv[sys.argv.index("--seed") + 1])
                       if "--seed" in sys.argv else 0)
        print(f"[{name}] outcome={res['outcome']} kill_turn={res['kill_turn']} "
              f"turns={res['turns']} boss_hp={res['boss_hp']} "
              f"repeat={res['counters'].get('repeat_coin', 0)} "
              f"sinking_sp={res['counters'].get('sinking_sp_damage', 0)} "
              f"ego={res['counters'].get('ego_use', 0)}")
    if "--replay" in sys.argv:
        n = int(sys.argv[sys.argv.index("--replay") + 1]) if len(sys.argv) > sys.argv.index("--replay") + 1 else 3
        res = run_line(content, base)
        rep = export_replay(res["battle"])
        print(format_replay_text(rep, max_events=n * 200))


if __name__ == "__main__":
    main()
