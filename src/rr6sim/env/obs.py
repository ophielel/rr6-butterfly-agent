"""观察空间（计划书 §13）。

第一版观察 = 定长 float 向量 + 同名特征表（names），
方便训练时按名字解释，也方便论文里画「沉沦强度曲线 / 重投次数曲线」。
**不包含任何未来随机数信息**（计划书明确要求）。
"""

from __future__ import annotations

from ..core.status import (BUTTERFLY, DEAD_BUTTERFLY, DESPAIR, FUTURE, PAST,
                           PRESENT, SINKING, TIMEGAP)
from ..core.unit import Unit

ALLY_STATUS_KEYS = ["sinking", "fragile", "strong", "despair", "blessing", "offense_level_down"]
ALLY_RESOURCE_KEYS = [("living_butterfly", 10.0), ("lantern", 6.0), ("hikari", 9.0),
                      ("harmony", 9.0), ("ammo", 6.0)]
PHANTOM_ORDER = ["phantom_past", "phantom_present", "phantom_future"]
FORM_ORDER = ["neutral", "past", "present", "future"]


def build_observation(battle) -> tuple:
    """返回 ``(values, names)``。"""
    st = battle.state
    vals: list = []
    names: list = []

    def add(name: str, value: float) -> None:
        names.append(name)
        vals.append(float(value))

    # ---------------- 全局 ----------------
    add("turn", st.turn / 10.0)
    add("turns_left", max(0, st.config.max_turns - st.turn) / 10.0)
    add("ally_alive", sum(1 for u in st.allies if u.alive) / 7.0)
    add("phantom_alive", sum(1 for u in st.phantoms() if u.alive) / 3.0)

    # ---------------- 我方 ----------------
    for u in st.allies:
        p = f"ally[{u.uid}]"
        add(f"{p}.present", 1.0)
        add(f"{p}.alive", 1.0 if u.alive else 0.0)
        add(f"{p}.hp_pct", u.hp_pct())
        add(f"{p}.sp", u.sp / 45.0)
        add(f"{p}.staggered", 1.0 if u.staggered else 0.0)
        for s in u.slots:
            add(f"{p}.slot{s.index}.speed", s.speed / 10.0)
            # 技能候选 one-hot（相对于该人格自己的牌组顺序）
            ident = battle.content.identity(u.identity)
            deck = [sk.sid for sk in ident.skills] + [ident.guard]
            for sid in deck:
                add(f"{p}.slot{s.index}.choice[{sid}]", 1.0 if sid in s.skill_choices else 0.0)
            add(f"{p}.slot{s.index}.chosen_ego", 1.0 if s.choice_kind.value == "ego" else 0.0)
        for eid in u.ego_ids:
            ego = battle.content.ego(eid)
            add(f"{p}.ego[{eid}].usable", 1.0 if u.sp >= ego.sp_cost else 0.0)
            add(f"{p}.ego[{eid}].cost", ego.sp_cost / 45.0)
        for key, scale in ALLY_RESOURCE_KEYS:
            if key in u.res:
                add(f"{p}.res[{key}]", u.res.get(key, 0) / scale)
        for key in ALLY_STATUS_KEYS:
            stk = u.statuses.get(key)
            add(f"{p}.status[{key}].potency", (stk.potency if stk else 0) / 5.0)
            add(f"{p}.status[{key}].count", (stk.count if stk else 0) / 5.0)
        add(f"{p}.guard", 1.0 if u.guard else 0.0)
        add(f"{p}.ego_used", 1.0 if u.ego_used_this_turn else 0.0)

    # ---------------- 本体 ----------------
    boss = st.boss()
    b = "boss"
    if boss is None:
        add(f"{b}.present", 0.0)
    else:
        add(f"{b}.present", 1.0)
        add(f"{b}.alive", 1.0 if boss.alive else 0.0)
        add(f"{b}.hp_pct", boss.hp_pct())
        add(f"{b}.hp", boss.hp / max(1, boss.max_hp))
        add(f"{b}.sp", boss.sp / 45.0)
        add(f"{b}.staggered", 1.0 if boss.staggered else 0.0)
        add(f"{b}.stagger_index", boss.stagger_index / 4.0)
        add(f"{b}.stack_index", boss.state.get("stack_threshold_index", 0) / 4.0)
        form = boss.state.get("form", "neutral")
        for f in FORM_ORDER:
            add(f"{b}.form[{f}]", 1.0 if form == f else 0.0)
        for key in (PAST, PRESENT, FUTURE):
            add(f"{b}.stack[{key}]", boss.status_count(key) / 10.0)
        for key in (TIMEGAP, SINKING, BUTTERFLY, DEAD_BUTTERFLY, "fragile", "strong"):
            stk = boss.statuses.get(key)
            add(f"{b}.status[{key}].potency", (stk.potency if stk else 0) / 5.0)
            add(f"{b}.status[{key}].count", (stk.count if stk else 0) / 5.0)
        for s in boss.slots:
            add(f"{b}.slot{s.index}.speed", s.speed / 10.0)
            add(f"{b}.slot{s.index}.cancelled", 1.0 if s.cancelled else 0.0)
            add(f"{b}.slot{s.index}.acted", 1.0 if s.acted else 0.0)
            for sid in (boss.state.get("skill_pool") or []):
                add(f"{b}.slot{s.index}.skill[{sid}]", 1.0 if s.choice_id == sid else 0.0)

    # ---------------- 三幻影 ----------------
    for uid in PHANTOM_ORDER:
        ph = st.unit(uid)
        p = f"phantom[{uid}]"
        if ph is None:
            add(f"{p}.present", 0.0)
            continue
        add(f"{p}.present", 1.0)
        add(f"{p}.alive", 1.0 if ph.alive else 0.0)
        add(f"{p}.hp_pct", ph.hp_pct())
        add(f"{p}.targeted", 1.0 if ph.target_of_turn else 0.0)
        add(f"{p}.acts", 1.0 if (ph.slots and not ph.slots[0].cancelled) else 0.0)
        add(f"{p}.speed", (ph.slots[0].speed if ph.slots else 0) / 10.0)
        if boss is not None and ph.time_type:
            add(f"{p}.stack", boss.status_count(ph.time_type) / 10.0)
    return vals, names


def summarize(battle) -> dict:
    """给日志/调试用的紧凑局面摘要。"""
    st = battle.state
    boss = st.boss()
    return {
        "turn": st.turn,
        "boss_hp": boss.hp if boss else 0,
        "boss_sp": boss.sp if boss else 0,
        "form": boss.state.get("form") if boss else "",
        "stacks": {k: boss.status_count(k) for k in (PAST, PRESENT, FUTURE)} if boss else {},
        "sinking": (boss.statuses.get(SINKING).potency if boss and SINKING in boss.statuses else 0),
        "timegap": boss.status_count(TIMEGAP) if boss else 0,
        "allies_alive": sum(1 for u in st.allies if u.alive),
    }
