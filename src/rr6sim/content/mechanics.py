"""实验核心机制的自定义 handler（计划书 §8：极特殊机制直接写 handler）。

这里的每个 handler 都对应 wiki.gg 上的一段具体文本，见 docs/audit_report.md。
之所以不写成通用效果组合，是因为这些机制涉及跨单位读写（攻击者回 SP、
无 SP 单位转 Gloom 伤害、Living/Departed 转换），用数据 DSL 表达会绕且易错。
"""

from __future__ import annotations

import math

from ..core.context import Ctx
from ..core.damage import deal
from ..core.effects import register_handler
from ..core.enums import DamageType, Sin
from ..core.status import BUTTERFLY, SINKING


# ---------------------------------------------------------------------------
# Sinking
# ---------------------------------------------------------------------------
def h_sinking_trigger(eff: dict, ctx: Ctx) -> None:
    """沉沦触发（wiki.gg/Sinking）：

    * 有 SP 单位：失去等同强度的 SP，层数 -1；
    * **无 SP 单位（Abnormality）：改为受到等同强度的 Gloom 伤害**
      （忽略物理伤害类型抗性，但仍受罪孽抗性影响），层数 -1。
    """
    owner = ctx.self_unit
    st = owner.statuses.get(SINKING)
    if st is None or st.count <= 0 or st.potency <= 0:
        return
    potency = st.potency
    if getattr(owner, "has_sanity", True):
        before = owner.sp
        owner.sp = max(-owner.max_sp, owner.sp - potency)
        ctx.battle.bump("sinking_sp_damage", potency)
        ctx.battle.log_sp(ctx, owner, before, owner.sp, {"kind": "sinking"})
    else:
        if not ctx.battle.config.sinking_vs_no_sp_deals_gloom_damage:
            return
        dealt = deal(ctx.battle, ctx.other_unit, owner, potency, Sin.GLOOM, DamageType.BLUNT,
                     ctx=ctx, origin="sinking", flat=True)
        ctx.battle.bump("sinking_gloom_damage", dealt)
    st.count = max(0, st.count - 1)
    if st.is_empty():
        owner.statuses.pop(SINKING, None)


# ---------------------------------------------------------------------------
# Butterfly（蝶 = 特殊 Sinking；Potency = The Living，Count = The Departed）
# ---------------------------------------------------------------------------
def h_butterfly_trigger(eff: dict, ctx: Ctx) -> None:
    """蝶的命中触发（wiki.gg/Sinking 表格）：

    * **攻击者回复 (The Living / 4) SP（最少 1，向下取整）**；
    * **若自身 SP < 0：每个 The Departed 造成 (Sinking Potency / 5) Gloom 伤害
      （上限 30，向下取整；无 SP 单位减半）**。
    """
    owner = ctx.self_unit
    attacker = ctx.other_unit
    st = owner.statuses.get(BUTTERFLY)
    if st is None:
        return
    living, departed = st.potency, st.count
    if attacker is not None and getattr(attacker, "has_sanity", True):
        heal = max(1, living // 4)
        before = attacker.sp
        attacker.sp = min(attacker.max_sp, attacker.sp + heal)
        if attacker.sp != before:
            ctx.battle.log_sp(ctx, attacker, before, attacker.sp, {"kind": "butterfly_heal"})
    if departed > 0 and getattr(owner, "has_sanity", True) and owner.sp < 0:
        sink_potency = owner.status_potency(SINKING)
        per = sink_potency // 5
        if per > 0:
            amount = min(30, per * departed)
            deal(ctx.battle, attacker, owner, amount, Sin.GLOOM, DamageType.BLUNT,
                 ctx=ctx, origin="butterfly", flat=True)
            ctx.battle.bump("butterfly_gloom_damage", amount)


def h_butterfly_turn_end(eff: dict, ctx: Ctx) -> None:
    """蝶的回合结束转换：

    Departed 归 0 → 获得等同 The Living 的 Sinking → The Living 转换为 The Departed。
    """
    owner = ctx.self_unit
    st = owner.statuses.get(BUTTERFLY)
    if st is None:
        return
    living = st.potency
    if living <= 0 and st.count <= 0:
        owner.statuses.pop(BUTTERFLY, None)
        return
    owner.add_status(SINKING, potency=living, count=0)
    st.count = living
    st.potency = 0
    if st.count <= 0:
        owner.statuses.pop(BUTTERFLY, None)


def h_inflict_butterfly(eff: dict, ctx: Ctx) -> None:
    """按 wiki 文本施加蝶：

    「When inflicting Butterfly using this Skill's effects: (Chance to flip Heads)% chance
    to inflict The Departed. If this unit did not inflict The Departed, inflict The Living
    instead. (calculates every Butterfly Stack independently)」

    即：每一层独立掷硬币 —— 正面 → The Departed（Count），否则 → The Living（Potency）。
    """
    amount = int(eff.get("amount", 1))
    for target in ctx.targets(eff.get("target", "other")):
        if not target.alive:
            continue
        p = 0.5
        if ctx.battle.config.san_per_point and ctx.self_unit is not None and getattr(ctx.self_unit, "has_sanity", True):
            from ..core.rng import heads_probability

            p = heads_probability(ctx.self_unit.sp, ctx.battle.config.san_per_point)
        departed = 0
        living = 0
        for _ in range(max(0, amount)):
            if ctx.battle.rng.chance(p):
                departed += 1
            else:
                living += 1
        target.add_status(BUTTERFLY, potency=living, count=departed)
        ctx.battle.log_status(ctx, target, BUTTERFLY, living, departed,
                              {"kind": "inflict_butterfly"})
        ctx.battle.bump("butterfly_inflicted", living + departed)


def h_spend_living_departed_burst(eff: dict, ctx: Ctx) -> None:
    """李箱「庄严哀悼」第 5 枚硬币：花光 The Living & The Departed 并结算追加伤害。

    wiki 文本：
    ``Spend all The Living & The Departed on self``
    - ``[On Hit] Deal Gloom damage equal to the sum of both Butterfly on target``
    - ``[On Hit] Deal Gloom damage equal to (The Living & The Departed spent by this Coin x 2)%
      of this Coin's final damage``
    """
    target = ctx.other_unit
    if target is None:
        return
    st = target.statuses.get(BUTTERFLY)
    spent = (st.potency + st.count) if st else 0
    if st is not None:
        target.statuses.pop(BUTTERFLY, None)
    if spent <= 0:
        return
    # 1) 等同两者之和的 Gloom 伤害
    deal(ctx.battle, ctx.self_unit, target, spent, Sin.GLOOM, DamageType.PIERCE,
         ctx=ctx, origin="butterfly_sum", flat=True)
    # 2) (spent × 2)% × 本硬币最终伤害
    mult = min(1.0, spent * 0.02)
    extra = int(math.floor(max(0, ctx.damage) * mult))
    if extra > 0:
        deal(ctx.battle, ctx.self_unit, target, extra, Sin.GLOOM, DamageType.PIERCE,
             ctx=ctx, origin="butterfly_spent", flat=True)
    ctx.battle.bump("butterfly_spent", spent)


# ---------------------------------------------------------------------------
# 自我伤害（和声：Heads Hit 时自身 4~8 HP，不触发混乱、不会低于 1）
# ---------------------------------------------------------------------------
def h_self_harm(eff: dict, ctx: Ctx) -> None:
    lo = int(eff.get("min", 0))
    hi = int(eff.get("max", lo))
    amount = ctx.battle.rng.randint(lo, hi)
    unit = ctx.self_unit
    max_loss = max(0, unit.hp - 1)
    loss = min(amount, max_loss)
    if loss <= 0:
        return
    unit.hp -= loss
    ctx.battle.log("damage", {"source": unit.uid, "target": unit.uid, "amount": loss,
                             "origin": "self_harm", "hp": unit.hp, "breakdown": None,
                             "no_stagger": True})
    ctx.battle.bump("self_harm", loss)


# ---------------------------------------------------------------------------
# 其他占位 handler（未实现，只记日志，避免静默吞掉机制）
# ---------------------------------------------------------------------------
def h_not_implemented(eff: dict, ctx: Ctx) -> None:
    ctx.battle.log("not_implemented", {
        "name": eff.get("name", eff.get("kind")),
        "note": eff.get("note", ""),
        "unit": ctx.self_unit.uid if ctx.self_unit else "",
        "target": ctx.other_unit.uid if ctx.other_unit else "",
    })
    ctx.battle.bump("not_implemented")


def register() -> None:
    register_handler("sinking_trigger", h_sinking_trigger)
    register_handler("butterfly_trigger", h_butterfly_trigger)
    register_handler("butterfly_turn_end", h_butterfly_turn_end)
    register_handler("inflict_butterfly", h_inflict_butterfly)
    register_handler("spend_living_departed_burst", h_spend_living_departed_burst)
    register_handler("self_harm", h_self_harm)
    register_handler("not_implemented", h_not_implemented)


register()
