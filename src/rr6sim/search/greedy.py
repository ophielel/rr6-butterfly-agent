"""Greedy 基线（计划书 §15.2）。

只看**即时期望伤害**：对每个槽位挑选当前能打出最大伤害的「技能/目标」组合。
它是最重要的对照组——我们希望最终算法明显超过它。

注意：Greedy 不会为了以后而建立沉沦/蝶/状态栈，这正是实验要对比的地方。
"""

from __future__ import annotations

from ..core.enums import CoinKind, SlotKind
from ..core.rng import heads_probability


def expected_damage(battle, actor, skill, target) -> float:
    p_heads = heads_probability(actor.sp, battle.config.san_per_point)
    total = 0.0
    res = target.resistance(skill.damage_type, skill.sin)
    for coin in skill.coins:
        favorable = p_heads if coin.kind is CoinKind.POSITIVE else (1.0 - p_heads)
        hit_mult = 0.5 + 0.5 * favorable
        total += coin.damage * hit_mult * res
    # 拼点胜负对伤害实现的影响：粗略地用「期望拼点威力」加权
    total *= 1.0
    return total


def score_action(battle, actor, action: dict, target: dict) -> float:
    if action["kind"] == "guard":
        return -1.0
    if action["kind"] == "ego":
        skill = battle.content.ego(action["id"]).variant(bool(action.get("corrosion")))
    else:
        skill = battle.content.skill(action["id"])
    if skill is None:
        return -1.0
    tgt = battle.unit(target["uid"])
    if tgt is None:
        return -1.0
    score = expected_damage(battle, actor, skill, tgt)
    if action["kind"] == "ego":
        cost = battle.content.ego(action["id"])
        sp_cost = cost.corrosion_sp_cost if action.get("corrosion") else cost.sp_cost
        score -= sp_cost * 0.5  # SP 是真实代价（计划书 §21）
    if target.get("clash"):
        score *= 1.15  # 能拼点赢的话更划算
    # 幻影伤害会转移给本体，但本体血量才是目标：等同看待
    return score


def greedy_plan(battle) -> list:
    """为所有我方槽位生成一条贪心计划。"""
    plan = []
    for u in battle.state.allies:
        if not u.alive:
            continue
        for slot in u.slots:
            if slot.cancelled or slot.choice_id:
                continue
            actions = battle.legal_actions(slot)
            targets = battle.legal_targets(slot)
            if not actions:
                continue
            best = None
            best_score = float("-inf")
            for a in actions:
                if a["kind"] == "guard":
                    if best is None:
                        best = (a, {"uid": "", "slot": -1})
                        best_score = max(best_score, -1.0)
                    continue
                for t in targets:
                    s = score_action(battle, u, dict(a, slot=slot.index), t)
                    if s > best_score:
                        best_score = s
                        best = (a, t)
            if best is None:
                best = ({"kind": "guard", "id": "guard", "corrosion": False}, {"uid": "", "slot": -1})
            a, t = best
            plan.append({
                "owner": u.uid, "slot": slot.index, "kind": a["kind"], "id": a["id"],
                "corrosion": bool(a.get("corrosion")), "target": t.get("uid", ""),
                "target_slot": int(t.get("slot", -1)),
            })
    return plan


def run_greedy(content, config, seed: int = 0, max_turns: int = None) -> dict:
    """跑一整局贪心，返回结果摘要。"""
    from ..simulate import new_battle

    battle = new_battle(content, config, seed)
    battle.log_enabled = True
    limit = max_turns or config.max_turns
    while not battle.state.is_terminal() and battle.state.turn <= limit:
        plan = greedy_plan(battle)
        from ..simulate import apply_plan

        apply_plan(battle, plan)
        battle.resolve_turn()
        if battle.state.is_terminal():
            break
        battle.begin_turn()
    boss = battle.state.boss()
    return {
        "seed": seed,
        "outcome": battle.state.outcome.value,
        "turns": battle.state.turn,
        "boss_hp": boss.hp if boss else 0,
        "kill_turn": battle.state.terminal.get("kill_turn"),
        "counters": dict(battle.state.counters),
        "battle": battle,
    }
