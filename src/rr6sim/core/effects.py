"""效果（Effect）执行器。

计划书 §8：**小型 Effect 集合 + 少量特殊 handler**，不做脚本语言。
每个效果都是纯数据 dict：::

    {"kind": "add_status", "key": "sinking", "potency": 2, "count": 2,
     "target": "other", "when": "on_hit", "if": {...}}

``when`` 用来绑定时点（由引擎在对应时点筛选），``if`` 是条件（见 conditions.py）。
特殊机制（生蝶弹药、幻影状态栈衰减…）以 handler 形式注册进来。
"""

from __future__ import annotations

from typing import Callable, Optional

from .conditions import eval_condition
from .context import Ctx
from .damage import deal
from .enums import DamageType, Sin

Handler = Callable[[dict, Ctx], None]
HANDLERS: dict[str, Handler] = {}

#: 统计计数器：replay 里要能回答「重复硬币到底触发了多少次」
COUNTERS = {
    "repeat_coin": 0,
    "sinking_trigger": 0,
    "butterfly_trigger": 0,
    "phantom_stack_decay": 0,
    "phantom_restore": 0,
    "form_switch": 0,
    "ego_use": 0,
    "stack_decay": 0,
}


def reset_counters() -> None:
    for k in COUNTERS:
        COUNTERS[k] = 0


def register_handler(kind: str, fn: Handler) -> None:
    HANDLERS[kind] = fn


def apply_effects(effects, ctx: Ctx) -> None:
    for eff in effects or ():
        if isinstance(eff, str):
            eff = {"kind": eff}
        if not isinstance(eff, dict):
            raise TypeError(f"效果必须是 dict 或 str，收到 {type(eff)}")
        if not eval_condition(eff.get("if"), ctx):
            continue
        kind = eff.get("kind")
        if not kind:
            continue
        fn = HANDLERS.get(kind)
        if fn is None:
            raise KeyError(f"未注册的效果 kind: {kind}")
        fn(eff, ctx)


def run_hooks(effects, ctx: Ctx, when: str) -> None:
    """执行绑定在指定时点的效果。"""
    sel = [e for e in (effects or ()) if isinstance(e, dict) and e.get("when") == when]
    if sel:
        apply_effects(sel, ctx)


# ---------------------------------------------------------------------------
# 数值抽取
# ---------------------------------------------------------------------------

def _amount(eff: dict, ctx: Ctx, key: str = "amount", default: int = 0) -> int:
    if key in eff:
        return int(eff[key])
    if "from_status" in eff:
        c = eff["from_status"]
        u = ctx.owner(c.get("who", "other"))
        if u is None:
            return 0
        st = u.statuses.get(c["key"])
        if st is None:
            return 0
        base = st.potency if c.get("field", "potency") == "potency" else st.count
        return int(base * float(c.get("mult", 1.0)))
    if "from_resource" in eff:
        c = eff["from_resource"]
        u = ctx.owner(c.get("who", "self"))
        return int((u.res.get(c["key"], 0) if u else 0) * float(c.get("mult", 1.0)))
    return default


def _targets(eff: dict, ctx: Ctx, default: str = "other") -> list:
    tok = eff.get("target", default)
    if isinstance(tok, list):
        out = []
        for t in tok:
            out.extend(ctx.targets(t))
        return out
    return ctx.targets(tok)


def _sin(eff: dict, ctx: Ctx) -> Sin:
    if "sin" in eff:
        return Sin(eff["sin"])
    if ctx.skill is not None:
        return ctx.skill.sin
    return Sin.WRATH


def _dtype(eff: dict, ctx: Ctx) -> DamageType:
    if "damage_type" in eff:
        return DamageType(eff["damage_type"])
    if ctx.skill is not None:
        return ctx.skill.damage_type
    return DamageType.BLUNT


# ---------------------------------------------------------------------------
# 通用 handler
# ---------------------------------------------------------------------------

def _h_add_status(eff: dict, ctx: Ctx) -> None:
    key = eff["key"]
    potency = _amount(eff, ctx, "potency", int(eff.get("potency", 0)))
    count = _amount(eff, ctx, "count", int(eff.get("count", 0)))
    for u in _targets(eff, ctx):
        u.add_status(key, potency, count)
        ctx.battle.log_status(ctx, u, key, potency, count, eff)


def _h_set_status(eff: dict, ctx: Ctx) -> None:
    key = eff["key"]
    potency = int(eff.get("potency", 0))
    count = int(eff.get("count", 0))
    for u in _targets(eff, ctx):
        u.set_status(key, potency, count)


def _h_remove_status(eff: dict, ctx: Ctx) -> None:
    for u in _targets(eff, ctx):
        u.clear_status(eff["key"])


def _h_lose_sp(eff: dict, ctx: Ctx) -> None:
    amt = _amount(eff, ctx, "amount")
    if amt <= 0:
        return
    for u in _targets(eff, ctx):
        before = u.sp
        u.sp = max(-u.max_sp, u.sp - amt)
        ctx.battle.log_sp(ctx, u, before, u.sp, eff)
    if eff.get("counter"):
        ctx.battle.bump(eff["counter"], amt)


def _h_heal_sp(eff: dict, ctx: Ctx) -> None:
    amt = _amount(eff, ctx, "amount")
    if amt <= 0:
        return
    for u in _targets(eff, ctx):
        before = u.sp
        u.sp = min(u.max_sp, u.sp + amt)
        ctx.battle.log_sp(ctx, u, before, u.sp, eff)


def _h_heal_hp(eff: dict, ctx: Ctx) -> None:
    for u in _targets(eff, ctx):
        if "pct" in eff:
            amt = int(u.max_hp * float(eff["pct"]))
        else:
            amt = _amount(eff, ctx, "amount")
        u.hp = min(u.max_hp, u.hp + amt)


def _h_deal_damage(eff: dict, ctx: Ctx) -> None:
    amt = _amount(eff, ctx, "amount")
    if amt <= 0:
        return
    sin = _sin(eff, ctx)
    dtype = _dtype(eff, ctx)
    for u in _targets(eff, ctx):
        deal(ctx.battle, ctx.self_unit, u, amt, sin, dtype, ctx=ctx,
             origin=eff.get("origin", "effect"))
    if eff.get("counter"):
        ctx.battle.bump(eff["counter"], max(0, ctx.damage) or amt)


def _h_add_resource(eff: dict, ctx: Ctx) -> None:
    key = eff["key"]
    amt = _amount(eff, ctx, "amount")
    for u in _targets(eff, ctx, default="self"):
        lo = int(eff.get("min", -10 ** 9))
        hi = int(eff.get("max", 10 ** 9))
        u.res[key] = max(lo, min(hi, u.res.get(key, 0) + amt))


def _h_set_resource(eff: dict, ctx: Ctx) -> None:
    for u in _targets(eff, ctx, default="self"):
        u.res[eff["key"]] = int(eff.get("value", 0))


def _h_consume_resource(eff: dict, ctx: Ctx) -> None:
    """扣除资源；``scaled`` 为 True 时把实际扣除量写入 ctx.note，供后续效果使用。

    默认作用于 ``self``（人格专属资源默认是自己的）。
    """
    key = eff["key"]
    for u in _targets(eff, ctx, default="self"):
        have = u.res.get(key, 0)
        want = _amount(eff, ctx, "amount")
        spent = min(have, want)
        u.res[key] = have - spent
        ctx.note[f"consumed:{key}"] = spent
        ctx.battle.bump(f"consumed:{key}", spent)


def _h_note_scale(eff: dict, ctx: Ctx) -> None:
    """把「上一步消耗掉的资源量」乘上系数写入伤害修正。"""
    src = eff.get("from", "consumed")
    key = eff.get("key", "")
    val = ctx.note.get(f"{src}:{key}", 0)
    if "damage" in eff:
        ctx.damage_mod += int(val * float(eff["damage"]))
    if "potency" in eff:
        ctx.note["scaled_potency"] = ctx.note.get("scaled_potency", 0) + int(val * float(eff["potency"]))


def _h_modify_power(eff: dict, ctx: Ctx) -> None:
    ctx.power_mod += _amount(eff, ctx, "amount")


def _h_modify_damage(eff: dict, ctx: Ctx) -> None:
    ctx.damage_mod += _amount(eff, ctx, "amount")


def _h_modify_damage_mult(eff: dict, ctx: Ctx) -> None:
    ctx.damage_mult *= float(eff.get("mult", 1.0))


def _h_repeat_coin(eff: dict, ctx: Ctx) -> None:
    if not ctx.battle.config.repeat_coin_enabled:
        return
    if ctx.is_repeat_throw and not eff.get("allow_recursive"):
        # 「重复投掷」产生的硬币不再触发新的重复投掷，避免无限递归
        return
    times = int(eff.get("times", 1))
    if times <= 0:
        return
    if eff.get("all_coins"):
        # 技能级「所有硬币重复投掷」：写进 proto.note，由 strike 读取
        # （多次触发会累加，例如「每 10 级沉沦重复 1 次，最多 2 次」）
        ctx.note["repeat_all"] = int(ctx.note.get("repeat_all", 0)) + times
    else:
        ctx.repeat_extra += times
    # 实际重复投掷次数由 strike 统计（battle.counters["repeat_coin"]）


def _h_add_coin(eff: dict, ctx: Ctx) -> None:
    ctx.extra_coins += int(eff.get("count", 1))


def _h_set_state(eff: dict, ctx: Ctx) -> None:
    for u in _targets(eff, ctx):
        val = eff.get("value")
        if isinstance(val, dict) and val.get("from") == "note":
            val = ctx.note.get(val["key"])
        u.state[eff["key"]] = val


def _h_log_event(eff: dict, ctx: Ctx) -> None:
    ctx.battle.log("event", {
        "name": eff.get("name", "event"),
        "data": {k: v for k, v in eff.items() if k not in ("kind", "when", "if")},
        "actor": ctx.self_unit.uid if ctx.self_unit else "",
        "target": ctx.other_unit.uid if ctx.other_unit else "",
    })


def _h_branch(eff: dict, ctx: Ctx) -> None:
    """条件分支：``branch_if`` 成立执行 ``then``，否则执行 ``else``。

    注意与效果自身的 ``if`` 区分：``if`` 为假时整条效果会被跳过，
    ``branch_if`` 只决定走哪个分支。
    """
    if eval_condition(eff.get("branch_if"), ctx):
        apply_effects(eff.get("then"), ctx)
    else:
        apply_effects(eff.get("else"), ctx)


def _h_change_form(eff: dict, ctx: Ctx) -> None:
    ctx.battle.change_form(force=eff.get("to"))


def _h_add_stack(eff: dict, ctx: Ctx) -> None:
    """过去 / 现在 / 未来状态栈增减。

    ``time`` 可以是 past / present / future / all / highest / target_time。
    ``once_per_coin`` 保证「每枚硬币只减一次对应层数」（计划书 §18.1）。
    """
    if eff.get("once_per_coin") and ctx.note.get("stack_decayed"):
        return
    amount = _amount(eff, ctx, "amount")
    times = int(eff.get("times", 1))
    times = max(1, min(times, int(eff.get("max_times", 99))))
    if eff.get("per_status"):
        c = eff["per_status"]
        u = ctx.owner(c.get("who", "other"))
        st = u.statuses.get(c["key"]) if u else None
        if st is None:
            return
        base = st.potency if c.get("field", "potency") == "potency" else st.count
        times = max(1, min(times, base // int(c.get("per", 1))))
    ctx.battle.add_stacks(amount * times, eff.get("time", "all"), ctx)
    if eff.get("once_per_coin"):
        ctx.note["stack_decayed"] = True


def _h_transfer_damage(eff: dict, ctx: Ctx) -> None:
    mult = float(eff.get("mult", 1.0))
    if ctx.damage <= 0:
        return
    boss = ctx.battle.unit("boss")
    if boss is None or not boss.alive:
        return
    ctx.battle.apply_damage(ctx.self_unit, boss, int(ctx.damage * mult), None,
                            origin=eff.get("origin", "transfer"))


def _h_force_stagger(eff: dict, ctx: Ctx) -> None:
    for u in _targets(eff, ctx):
        ctx.battle.force_stagger(u)


def _h_ego_resist_override(eff: dict, ctx: Ctx) -> None:
    if not ctx.battle.config.ego_resistance_override:
        return
    for u in _targets(eff, ctx):
        eid = eff.get("ego") or u.state.get("last_ego")
        ego = ctx.battle.content.ego(eid) if eid else None
        if ego is None:
            return
        u.resist_override = dict(ego.resist_override)
        ctx.battle.log("ego_resist_override", {"unit": u.uid, "ego": eid,
                                               "override": {k.value: v for k, v in ego.resist_override.items()}})


def _h_sum_status(eff: dict, ctx: Ctx) -> None:
    """把若干状态的强度/层数求和，每满 ``per`` 点就把 ``then`` 中的效果执行一次。

    例：目标每有 3 级沉沦强度，就重复投掷 1 枚硬币。
    """
    total = 0
    for c in eff.get("of", []):
        u = ctx.owner(c.get("who", "other"))
        st = u.statuses.get(c["key"]) if u else None
        if st is None:
            continue
        total += st.potency if c.get("field", "potency") == "potency" else st.count
    per = int(eff.get("per", 1)) or 1
    times = total // per
    if eff.get("max") is not None:
        times = min(times, int(eff["max"]))
    if times <= 0:
        return
    then = list(eff.get("then") or [])
    for _ in range(times):
        apply_effects(then, ctx)


# ---------------------------------------------------------------------------

def _install() -> None:
    register_handler("add_status", _h_add_status)
    register_handler("set_status", _h_set_status)
    register_handler("remove_status", _h_remove_status)
    register_handler("lose_sp", _h_lose_sp)
    register_handler("heal_sp", _h_heal_sp)
    register_handler("heal_hp", _h_heal_hp)
    register_handler("deal_damage", _h_deal_damage)
    register_handler("add_resource", _h_add_resource)
    register_handler("set_resource", _h_set_resource)
    register_handler("consume_resource", _h_consume_resource)
    register_handler("note_scale", _h_note_scale)
    register_handler("modify_power", _h_modify_power)
    register_handler("modify_damage", _h_modify_damage)
    register_handler("modify_damage_mult", _h_modify_damage_mult)
    register_handler("repeat_coin", _h_repeat_coin)
    register_handler("add_coin", _h_add_coin)
    register_handler("set_state", _h_set_state)
    register_handler("log_event", _h_log_event)
    register_handler("branch", _h_branch)
    register_handler("change_form", _h_change_form)
    register_handler("add_stack", _h_add_stack)
    register_handler("transfer_damage", _h_transfer_damage)
    register_handler("force_stagger", _h_force_stagger)
    register_handler("ego_resist_override", _h_ego_resist_override)
    register_handler("sum_status", _h_sum_status)


_install()
