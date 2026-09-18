"""条件表达式：数据文件里的 ``if`` 字段。

条件同样是纯数据（dict），由 ``eval_condition`` 解释。
支持的写法见 ``docs/mechanics_notes.md``。
"""

from __future__ import annotations

from typing import Any, Optional

from .context import Ctx


def _unit_of(ctx: Ctx, who: str):
    return ctx.owner(who)


def eval_condition(cond: Optional[dict], ctx: Ctx) -> bool:
    if not cond:
        return True
    if not isinstance(cond, dict):
        raise TypeError(f"条件必须是 dict，收到 {type(cond)}")

    if "all" in cond:
        return all(eval_condition(c, ctx) for c in cond["all"])
    if "any" in cond:
        return any(eval_condition(c, ctx) for c in cond["any"])
    if "not" in cond:
        return not eval_condition(cond["not"], ctx)

    if "status" in cond:
        c = cond["status"]
        u = _unit_of(ctx, c.get("who", "other"))
        if u is None:
            return False
        st = u.statuses.get(c["key"])
        if st is None:
            return False
        if "potency_gte" in c and st.potency < c["potency_gte"]:
            return False
        if "count_gte" in c and st.count < c["count_gte"]:
            return False
        if "potency_lte" in c and st.potency > c["potency_lte"]:
            return False
        if "count_lte" in c and st.count > c["count_lte"]:
            return False
        return True

    if "resource" in cond:
        c = cond["resource"]
        u = _unit_of(ctx, c.get("who", "self"))
        if u is None:
            return False
        val = u.res.get(c["key"], 0)
        if "gte" in c and val < c["gte"]:
            return False
        if "lte" in c and val > c["lte"]:
            return False
        if "eq" in c and val != c["eq"]:
            return False
        return True

    if "hp_pct" in cond:
        c = cond["hp_pct"]
        u = _unit_of(ctx, c.get("who", "other"))
        if u is None:
            return False
        pct = u.hp_pct()
        if "lte" in c and pct > c["lte"]:
            return False
        if "gte" in c and pct < c["gte"]:
            return False
        return True

    if "sp" in cond:
        c = cond["sp"]
        u = _unit_of(ctx, c.get("who", "other"))
        if u is None:
            return False
        if "lte" in c and u.sp > c["lte"]:
            return False
        if "gte" in c and u.sp < c["gte"]:
            return False
        return True

    if "coin_heads" in cond:
        return ctx.coin_heads == cond["coin_heads"]
    if "coin_index_gte" in cond:
        return ctx.coin_index >= cond["coin_index_gte"]
    if "coin_index_lte" in cond:
        return ctx.coin_index <= cond["coin_index_lte"]

    if "is_phantom" in cond:
        u = _unit_of(ctx, cond.get("who", "other"))
        return bool(u and u.kind == "phantom") == cond["is_phantom"]
    if "target_kind" in cond:
        u = _unit_of(ctx, cond.get("who", "other"))
        return bool(u and u.kind == cond["target_kind"])
    if "time_type" in cond:
        u = _unit_of(ctx, cond.get("who", "other"))
        return bool(u and u.time_type == cond["time_type"])
    if "form_is" in cond:
        boss = ctx.battle.unit("boss")
        return bool(boss and boss.state.get("form") == cond["form_is"])
    if "turn" in cond:
        c = cond["turn"]
        t = ctx.battle.state.turn
        if "gte" in c and t < c["gte"]:
            return False
        if "lte" in c and t > c["lte"]:
            return False
        return True
    if "staggered" in cond:
        u = _unit_of(ctx, cond.get("who", "other"))
        return bool(u and u.staggered) == cond["staggered"]
    if "chance" in cond:
        return ctx.battle.rng.chance(float(cond["chance"]))
    if "skill_tag" in cond:
        return bool(ctx.skill and cond["skill_tag"] in (ctx.skill.tags or []))
    if "config" in cond:
        c = cond["config"]
        cfg = ctx.battle.config
        for k, v in c.items():
            if getattr(cfg, k, None) != v:
                return False
        return True
    if "always" in cond:
        return bool(cond["always"])

    raise KeyError(f"未知条件: {sorted(cond)}")
