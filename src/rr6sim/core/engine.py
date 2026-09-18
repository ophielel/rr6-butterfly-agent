"""战斗引擎：回合流程 / 拼点 / 逐枚硬币结算 / 状态触发 / 罗生蝶机制。

这是模拟器的心脏。计划书 §7 的时点表在这里落地：

TurnStart -> SpeedRoll -> SkillChoicesReady -> (玩家规划) -> CombatStart
  -> BeforeClash -> ClashRoll -> ClashWin/ClashLose
  -> BeforeAttack -> BeforeCoin -> CoinRoll(Heads/Tails) -> CoinHit -> AfterCoin
  -> AfterAttack -> UnitStagger / UnitDeath -> TurnEnd

所有伤害都必须走「逐枚硬币」路径（§9.14 / §9.15），
不允许任何地方「先算一个总伤害再扣 HP」。
"""

from __future__ import annotations

import math
from typing import Optional

from .conditions import eval_condition
from .context import Ctx
from .damage import DamageBreakdown, deal
from .effects import apply_effects, run_hooks
from .enums import (CoinKind, DamageType, Form, Outcome, Phase, Side, Sin,
                    SlotKind, TargetMode, TimeType, Timing)
from .rng import SplitMix64, heads_probability
from .skill import Ego, Skill
from .state import BattleState
from .status import (BUTTERFLY, DEAD_BUTTERFLY, FUTURE, IN_THE_FUTURE, IN_THE_PAST,
                     IN_THE_PRESENT, PAST, PRESENT, TIMEGAP)
from .unit import ActionSlot, Unit, status_spec


class Battle:
    def __init__(self, state: BattleState, content, rng: Optional[SplitMix64] = None) -> None:
        self.state = state
        self.content = content
        self.config = state.config
        self.rng = rng if rng is not None else SplitMix64(state.rng_state or state.seed)
        self.log_enabled = True

    # ==================================================================
    # 基础设施
    # ==================================================================
    def sync(self) -> None:
        self.state.rng_state = self.rng.snapshot()

    def clone(self) -> "Battle":
        st = self.state.copy()
        if not self.log_enabled:
            st.log = []
        b = Battle(st, self.content, SplitMix64(self.rng.snapshot()))
        b.log_enabled = self.log_enabled
        return b

    def log(self, kind: str, data: dict) -> None:
        if not self.log_enabled:
            return
        entry = {"turn": self.state.turn, "kind": kind}
        for k, v in data.items():
            if k in ("kind", "turn"):
                continue
            entry[k] = v
        self.state.log.append(entry)

    def bump(self, key: str, amount: int = 1) -> None:
        self.state.counters[key] = self.state.counters.get(key, 0) + amount

    @property
    def counters(self) -> dict:
        return self.state.counters

    def log_status(self, ctx: Ctx, unit: Unit, key: str, potency: int, count: int,
                   eff: dict) -> None:
        self.log("status", {
            "unit": unit.uid, "status": key, "potency": potency, "count": count,
            "total_potency": unit.status_potency(key), "total_count": unit.status_count(key),
            "source": eff.get("kind"), "by": ctx.self_unit.uid if ctx.self_unit else "",
        })

    def log_sp(self, ctx: Ctx, unit: Unit, before: int, after: int, eff: dict) -> None:
        self.log("sp", {"unit": unit.uid, "before": before, "after": after,
                        "delta": after - before, "source": eff.get("kind")})

    # 查询 -------------------------------------------------------------
    def units_of(self, side: Side) -> list:
        return self.state.units_of(side)

    def unit(self, uid: str):
        return self.state.unit(uid)

    def allies(self) -> list:
        return self.state.allies

    def enemies(self) -> list:
        return self.state.enemies

    def boss(self):
        return self.state.boss()

    # ==================================================================
    # 回合开始
    # ==================================================================
    def begin_turn(self) -> None:
        st = self.state
        st.turn += 1
        st.plan = []
        st.phase = Phase.PLANNING
        self.bump("turns")

        for u in st.all_units():
            u.target_of_turn = False
            u.ego_used_this_turn = False
            u.state["egos_used_this_turn"] = []
            u.guard = False
            if u.side is Side.ALLY:
                u.resist_override = {}
            # 混乱恢复
            if u.staggered and st.turn > int(u.state.get("stagger_until_turn", 0)):
                u.staggered = False
                u.stagger_level = 0
            u.state["clash_wins_this_turn"] = 0
            # 幻影复原
            if u.kind == "phantom" and not u.alive:
                if st.turn >= int(u.state.get("revive_turn", 0)):
                    u.alive = True
                    u.hp = u.max_hp
                    self.log("phantom_revive", {"unit": u.uid})
            for s in u.slots:
                s.acted = False
                s.cancelled = False
                s.choice_kind = SlotKind.SKILL
                s.choice_id = ""
                s.corrosion = False
                s.target_uid = ""
                s.target_slot = -1
                s.redirected = False

        self.run_all_hooks(Timing.TURN_START)
        self.activate_time_state()
        self.roll_speeds()
        self.draw_skills()
        self.plan_enemy_actions()
        self.change_form()
        self.sync()

    # ------------------------------------------------------------------
    def roll_speeds(self) -> None:
        cfg = self.config
        for u in self.state.all_units():
            lo, hi = u.speed_range
            for i, slot in enumerate(u.slots):
                if cfg.speed_mode == "fixed":
                    slot.speed = min(hi, lo + i)
                else:
                    slot.speed = self.rng.randint(lo, hi)
        self.log("speeds", {"units": {u.uid: [s.speed for s in u.slots]
                                      for u in self.state.all_units()}})

    def draw_skills(self) -> None:
        for u in self.state.allies:
            ident = self.content.identity(u.identity)
            if ident is None:
                # 未注册人格（测试用假单位）：没有可抽的技能，只能守备
                for slot in u.slots:
                    slot.skill_choices = []
                continue
            q = self.state.deck_queue.setdefault(u.uid, [])
            for slot in u.slots:
                choices = []
                while len(choices) < 2:
                    if not q:
                        q.extend(self._deck_refill(ident))
                    choices.append(q.pop(0))
                slot.skill_choices = choices
        self.log("skill_choices", {"units": {u.uid: [list(s.skill_choices) for s in u.slots]
                                             for u in self.state.allies}})

    def _deck_refill(self, ident) -> list:
        deck = list(ident.deck)
        if self.config.skill_draw_mode == "rng":
            self.rng_shuffle(deck)
        return deck

    def rng_shuffle(self, seq: list) -> None:
        for i in range(len(seq) - 1, 0, -1):
            j = self.rng.randint(0, i)
            seq[i], seq[j] = seq[j], seq[i]

    # ------------------------------------------------------------------
    def plan_enemy_actions(self) -> None:
        """敌方行动（计划书课程 0：可以让 Boss 完全不动）。"""
        cfg = self.config
        for u in self.state.enemies:
            if not u.alive:
                continue
            if u.kind == "phantom" and not (cfg.phantom_acts and cfg.encounter_buffs.get("phantom_acts", True)):
                for s in u.slots:
                    s.cancelled = True
                continue
            for slot in u.slots:
                if u.staggered:
                    slot.cancelled = True
                    continue
                sid = self._pick_enemy_skill(u, slot)
                if sid is None:
                    slot.cancelled = True
                    continue
                slot.choice_kind = SlotKind.SKILL
                slot.choice_id = sid
                tgt_unit, tgt_slot = self._pick_enemy_target(u, slot)
                slot.target_uid = tgt_unit.uid if tgt_unit else ""
                slot.target_slot = tgt_slot
        self.log("enemy_intents", {"intents": {
            u.uid: [{"skill": s.choice_id, "target": s.target_uid, "slot": s.target_slot,
                     "speed": s.speed, "cancelled": s.cancelled} for s in u.slots]
            for u in self.state.enemies}})

    def _pick_enemy_skill(self, u: Unit, slot: ActionSlot) -> Optional[str]:
        pool = u.state.get("skill_pool") or []
        if not pool:
            return None
        mode = self.config.boss_ai if u.kind == "boss" else u.state.get("ai_mode", self.config.boss_ai)
        if mode == "none":
            return None
        if mode == "random":
            return self.rng.choice(pool)
        if mode == "greedy":
            return self._greedy_skill(u, pool)
        # script：按回合数循环固定牌序（Stage A 的确定性要求）；多槽位错开
        rotation = self._rotation_skill(u, slot)
        if rotation is not None:
            return rotation
        script = u.state.get("skill_script") or pool
        return script[(self.state.turn - 1 + slot.index) % len(script)]

    def _rotation_skill(self, u: Unit, slot: ActionSlot) -> Optional[str]:
        """真实 Imago 的三回合技能循环：按当前激活的时间状态与 HP 阶段选技能。"""
        rots = u.state.get("skill_rotations")
        if not rots:
            return None
        state_key = u.state.get("active_time_state") or "in_the_past"
        table = rots.get(state_key) or {}
        pct = u.hp_pct()
        if pct < 0.33:
            seq = table.get("below_33") or table.get("below_66") or table.get("normal")
        elif pct < 0.66:
            seq = table.get("below_66") or table.get("normal")
        else:
            seq = table.get("normal")
        if not seq:
            return None
        idx = int(u.state.get("cycle_turn", 0)) + slot.index
        return seq[idx % len(seq)]

    def _greedy_skill(self, u: Unit, pool: list) -> str:
        best, best_score = pool[0], -1.0
        target = self._first_ally()
        for sid in pool:
            sk = self.content.skill(sid)
            score = 0.0
            for coin in sk.coins:
                if target is None:
                    break
                heads_p = heads_probability(u.sp, self.config.san_per_point)
                exp_power = sk.base_power + coin.power * (heads_p if coin.kind is CoinKind.POSITIVE
                                                          else 1 - heads_p)
                score += exp_power * 0.1 + coin.damage
            if score > best_score:
                best, best_score = sid, score
        return best

    def _first_ally(self) -> Optional[Unit]:
        for u in self.state.allies:
            if u.alive:
                return u
        return None

    def _pick_enemy_target(self, u: Unit, slot: ActionSlot):
        if u.state.get("target_mode", "first") == "spread":
            alive = [a for a in self.state.allies if a.alive]
            if not alive:
                return None, -1
            return alive[(self.state.turn - 1 + slot.index) % len(alive)], 0
        mode = u.state.get("target_mode", "first")
        pool = [a for a in self.state.allies if a.alive]
        if not pool:
            return None, -1
        if mode == "random":
            tgt = self.rng.choice(pool)
        elif mode == "lowest_hp":
            tgt = min(pool, key=lambda a: a.hp)
        elif mode == "highest_threat":
            tgt = max(pool, key=lambda a: a.offense_level)
        else:
            tgt = pool[0]
        idx = slot.index % max(1, len(tgt.slots))
        return tgt, idx

    # ==================================================================
    # 规划（自回归）
    # ==================================================================
    def pending_slot(self) -> Optional[ActionSlot]:
        for u in self.state.allies:
            if not u.alive:
                continue
            for s in u.slots:
                if s.choice_id == "" and not s.cancelled:
                    return s
        return None

    def plan_complete(self) -> bool:
        return self.pending_slot() is None

    def skills_for(self, unit: Unit) -> list:
        """该单位本回合可用技能（普通技能池 + E.G.O）。"""
        ident = self.content.identity(unit.identity)
        return list(ident.skills)

    def legal_actions(self, slot: ActionSlot) -> list:
        """槽位可选的「行动」列表。

        E.G.O 的真实规则（docs/audit_report.md §4）：
        * **不因 SP 不足而被禁用**（SP 可以为负，扣到 −45 也允许）；
        * 觉醒 / 侵蚀由规则判定，不是在界面上勾选的开关；
        * 「显式选择侵蚀」= Overclock（花 1.5× 代价，得到去掉 Indiscriminate 的侵蚀技能）；
        * 同一回合同一 E.G.O 不能使用两次。
        """
        u = self._owner_of(slot)
        out = []
        for sid in slot.skill_choices:
            out.append({"kind": "skill", "id": sid, "corrosion": False})
        out.append({"kind": "guard", "id": "guard", "corrosion": False})
        used = list(u.state.get("egos_used_this_turn") or [])
        for eid in u.ego_ids:
            if eid in self.config.disabled_egos:
                continue
            ego = self.content.ego(eid)
            if ego is None:
                continue
            if not self.config.allow_same_ego_twice_per_turn and eid in used:
                continue
            out.append({"kind": "ego", "id": eid, "corrosion": False})
            out.append({"kind": "ego", "id": eid, "corrosion": True})
        return out

    def _owner_of(self, slot: ActionSlot) -> Unit:
        for u in self.state.all_units():
            for s in u.slots:
                if s is slot:
                    return u
        raise KeyError("槽位不属于任何单位")

    def legal_targets(self, slot: ActionSlot) -> list:
        """槽位可选目标：敌方单位（部位）的每个行动槽。

        关键：**「这个槽位会不会打出攻击」与「能不能被打」是两件事**。
        敌人因为混乱 / boss_ai=none / phantom_acts=false 而不行动时，
        它的槽位仍然是合法目标（只能单方面攻击）；
        只有单位死亡、部位被破坏（``targetable=False``）才不可选。
        """
        u = self._owner_of(slot)
        out = []
        for e in self.state.enemies:
            if not e.alive or e is u or not getattr(e, "targetable", True):
                continue
            for es in e.slots:
                if not getattr(es, "targetable", True):
                    continue
                can_clash = (not es.acted and not es.cancelled
                             and es.choice_kind is SlotKind.SKILL
                             and bool(es.target_uid)
                             and not e.staggered)
                clash = (can_clash and es.target_uid == u.uid
                         and (not self.config.clash_same_slot or es.target_slot == slot.index))
                redirect = can_clash and es.target_uid not in ("", u.uid)
                if redirect and self.config.enforce_redirect_speed:
                    victim = self._slot_owner(es.target_uid, es.target_slot)
                    if victim is not None and victim[1] is not None and victim[1].speed >= slot.speed:
                        continue
                out.append({"uid": e.uid, "slot": es.index, "clash": bool(clash),
                            "redirect": bool(redirect),
                            "one_sided": not (clash or redirect),
                            "acting": bool(can_clash)})
        return out

    def _slot_owner(self, uid: str, slot_index: int):
        u = self.unit(uid)
        if u is None or slot_index < 0 or slot_index >= len(u.slots):
            return None, None
        return u, u.slots[slot_index]

    def assign_action(self, slot: ActionSlot, kind: str, cid: str, corrosion: bool = False) -> None:
        slot.choice_kind = SlotKind(kind)
        slot.choice_id = cid
        slot.corrosion = corrosion

    def assign_target(self, slot: ActionSlot, uid: str, target_slot: int) -> None:
        slot.target_uid = uid
        slot.target_slot = target_slot
        self.state.plan.append({
            "slot": slot.index, "owner": self._owner_of(slot).uid,
            "kind": slot.choice_kind.value, "id": slot.choice_id,
            "corrosion": slot.corrosion, "target": uid, "target_slot": target_slot,
        })
        tgt = self.unit(uid)
        if tgt is not None:
            tgt.target_of_turn = True
            if tgt.kind == "phantom":
                self.state.flags.setdefault("targeted_phantoms", [])
                if tgt.uid not in self.state.flags["targeted_phantoms"]:
                    self.state.flags["targeted_phantoms"].append(tgt.uid)

    def build_skill(self, unit: Unit, slot: ActionSlot) -> Optional[Skill]:
        """把槽位的选择实例化成可执行的 Skill。"""
        if slot.choice_kind is SlotKind.GUARD:
            ident = self.content.identity(unit.identity)
            return self.content.skill(ident.guard)
        if slot.choice_kind is SlotKind.EGO:
            ego = self.content.ego(slot.choice_id)
            return ego.variant(slot.corrosion)
        return self.content.skill(slot.choice_id)

    # ==================================================================
    # 回合结算
    # ==================================================================
    def acting_order(self) -> list:
        entries = []
        for u in self.state.all_units():
            if not u.alive:
                continue
            for s in u.slots:
                if s.cancelled or s.acted:
                    continue
                side_rank = 0 if u.side is Side.ALLY else 1
                entries.append((s.speed, -side_rank, u.uid, s.index))
        entries.sort(key=lambda e: (-e[0], e[1], e[2], e[3]))
        return [(uid, idx) for _, _, uid, idx in entries]

    def resolve_turn(self) -> None:
        """按速度顺序结算本回合所有行动，然后进入回合结束。"""
        if self.state.phase is Phase.TERMINAL:
            return
        self.log("plan", {"entries": [dict(p) for p in self.state.plan]})
        self.log("combat_start", {"order": self.acting_order()})
        for uid, idx in self.acting_order():
            if self.state.phase is Phase.TERMINAL:
                break
            u = self.unit(uid)
            if u is None or not u.alive or u.staggered:
                continue
            slot = u.slots[idx]
            if slot.acted or slot.cancelled:
                continue
            self.execute_slot(u, slot)
            if self.check_end():
                break
        if not self.state.is_terminal():
            self.end_turn()

    # ------------------------------------------------------------------
    def execute_slot(self, unit: Unit, slot: ActionSlot) -> None:
        if slot.choice_kind is SlotKind.GUARD:
            unit.guard = True
            slot.acted = True
            self.log("guard", {"unit": unit.uid, "slot": slot.index})
            return
        if slot.choice_kind is SlotKind.EGO:
            ego = self.content.ego(slot.choice_id)
            use_corrosion, cost = self.plan_ego_use(unit, ego, slot)
            skill = ego.variant(use_corrosion)
            self.pay_ego_cost(unit, ego, slot, cost, use_corrosion)
        else:
            skill = self.build_skill(unit, slot)
        if skill is None:
            slot.acted = True
            return
        slot.acted = True

        target = self.unit(slot.target_uid)
        if target is None or not target.alive:
            # 目标已死：尝试落到同索引的敌方槽位，否则本次行动作废
            target = None
            for e in self.state.enemies:
                if e.alive and e.kind != "phantom":
                    target = e
                    break
            if target is None:
                self.log("action_cancelled", {"unit": unit.uid, "reason": "no_target"})
                return
            slot.target_uid = target.uid
            slot.target_slot = -1

        mode = TargetMode.ONE_SIDED
        tslot = None
        if 0 <= slot.target_slot < len(target.slots):
            tslot = target.slots[slot.target_slot]
        if (tslot is not None and not tslot.acted and not tslot.cancelled
                and tslot.choice_kind is SlotKind.SKILL
                and tslot.target_uid and self.unit(tslot.target_uid) is not None):
            mutual = (tslot.target_uid == unit.uid
                      and (not self.config.clash_same_slot
                           or tslot.target_slot == slot.index))
            if mutual and not target.staggered:
                mode = TargetMode.CLASH

        if mode is TargetMode.CLASH:
            self.execute_clash(unit, slot, skill, target, tslot)
        else:
            self.execute_attack(unit, slot, skill, target, mode)

    # ------------------------------------------------------------------
    def plan_ego_use(self, unit: Unit, ego, slot: ActionSlot) -> tuple:
        """决定这次 E.G.O 是觉醒还是侵蚀，以及实际 SP 代价。

        * ``slot.corrosion=True`` 表示玩家主动 **Overclock**：代价 ×1.5，使用侵蚀技能，
          但去掉 Indiscriminate（不会打到队友）。
        * 否则：若「当前 SP − 代价 ≤ −45」→ **必定侵蚀**；
          若 SP < 0 → 按概率侵蚀（config.corrosion_mode 可换成 deterministic）。
        """
        cfg = self.config
        base = ego.sp_cost
        if slot.corrosion:
            # Overclock：花 1.5× 罪孽资源与 SP，得到「去掉 Indiscriminate 的侵蚀技能」
            return True, int(math.ceil(base * cfg.overclock_multiplier))
        if cfg.corrosion_mode == "never":
            return False, base
        if unit.sp - base <= -unit.max_sp:
            # 强制侵蚀：代价按侵蚀技能自己的 SP 消耗（asanity / csanity）
            return True, ego.corrosion_sp_cost
        if cfg.corrosion_mode == "auto_only":
            return False, base
        if unit.sp < 0:
            chance = min(1.0, abs(unit.sp) / float(unit.max_sp) * cfg.corrosion_chance_at_min_sp * 2.0)
            if self.rng.chance(chance):
                return True, ego.corrosion_sp_cost
        return False, base

    def pay_ego_cost(self, unit: Unit, ego, slot: ActionSlot, cost: int,
                     use_corrosion: bool) -> None:
        before = unit.sp
        unit.sp = max(-unit.max_sp, unit.sp - cost)
        unit.ego_used_this_turn = True
        unit.state["last_ego"] = ego.eid
        used = list(unit.state.get("egos_used_this_turn") or [])
        if ego.eid not in used:
            used.append(ego.eid)
        unit.state["egos_used_this_turn"] = used
        self.bump("ego_use")
        if use_corrosion:
            self.bump("ego_corrosion")
        if slot.corrosion:
            self.bump("ego_overclock")
        self.log("ego_use", {"unit": unit.uid, "ego": ego.eid,
                             "corrosion": bool(use_corrosion),
                             "overclock": bool(slot.corrosion),
                             "sp_cost": cost, "sp_before": before, "sp_after": unit.sp})
        self.log_sp(Ctx(self, unit), unit, before, unit.sp, {"kind": "ego_cost"})
        # E.G.O 抗性覆盖：使用后自身罪孽抗性变为该 E.G.O 的抗性（持续到回合结束）
        if self.config.ego_resistance_override and ego.resist_override:
            unit.resist_override = dict(ego.resist_override)
        if self.config.ego_passives_enabled:
            ctx = Ctx(self, unit, None, ego.variant(use_corrosion), source=f"ego:{ego.eid}")
            run_hooks(ego.passive_effects, ctx, Timing.ON_USE)

    # ------------------------------------------------------------------
    def execute_attack(self, unit: Unit, slot: ActionSlot, skill: Skill, target: Unit,
                       mode: TargetMode) -> None:
        ctx = Ctx(self, unit, target, skill, source="skill", mode=mode)
        self.log("attack", {"unit": unit.uid, "slot": slot.index, "skill": skill.sid,
                            "target": target.uid, "mode": mode.value})
        run_hooks(skill.effects, ctx, Timing.ON_USE)
        self.run_status_hooks(unit, Timing.ON_USE, opponent=target, skill=skill)
        if self.check_end():
            return
        self.strike(unit, target, skill, ctx)

    # ------------------------------------------------------------------
    def execute_clash(self, a_unit: Unit, a_slot: ActionSlot, a_skill: Skill,
                      b_unit: Unit, b_slot: ActionSlot) -> None:
        b_skill = self.build_skill(b_unit, b_slot)
        b_slot.acted = True
        a_unit.state["_clash_bonus"] = 0
        b_unit.state["_clash_bonus"] = 0
        a_ctx = Ctx(self, a_unit, b_unit, a_skill, source="skill", mode=TargetMode.CLASH)
        b_ctx = Ctx(self, b_unit, a_unit, b_skill, source="skill", mode=TargetMode.CLASH)
        run_hooks(a_skill.effects, a_ctx, Timing.ON_USE)
        run_hooks(b_skill.effects, b_ctx, Timing.ON_USE)
        self.run_status_hooks(a_unit, Timing.ON_USE, opponent=b_unit, skill=a_skill)
        self.run_status_hooks(b_unit, Timing.ON_USE, opponent=a_unit, skill=b_skill)
        run_hooks(a_skill.effects, a_ctx, Timing.BEFORE_CLASH)
        run_hooks(b_skill.effects, b_ctx, Timing.BEFORE_CLASH)
        self.log("clash_start", {"a": a_unit.uid, "a_slot": a_slot.index, "a_skill": a_skill.sid,
                                 "b": b_unit.uid, "b_slot": b_slot.index, "b_skill": b_skill.sid})

        if self.config.clash_model == "reflex":
            winner, a_kept = self._clash_reflex(a_unit, a_skill, b_unit, b_skill)
            a_cracked = b_cracked = {}
        else:
            winner, a_kept, a_cracked, b_cracked = self._clash_advance(a_unit, a_skill, b_unit, b_skill)

        if winner == "a":
            before = a_unit.sp
            if a_unit.has_sanity:
                a_unit.sp = min(a_unit.max_sp, a_unit.sp + self.config.clash_win_sp_gain)
            if b_unit.has_sanity:
                b_unit.sp = max(-b_unit.max_sp, b_unit.sp + self.config.clash_lose_sp_loss)
            a_unit.state["clash_wins_this_turn"] = int(a_unit.state.get("clash_wins_this_turn", 0)) + 1
            self.log("clash_win", {"unit": a_unit.uid, "skill": a_skill.sid,
                                   "sp": a_unit.sp, "cracked": sorted(b_cracked)})
            self.log_sp(a_ctx, a_unit, before, a_unit.sp, {"kind": "clash_win"})
            a_ctx.clash_result = "win"
            b_ctx.clash_result = "lose"
            run_hooks(a_skill.effects, a_ctx, Timing.CLASH_WIN)
            run_hooks(b_skill.effects, b_ctx, Timing.CLASH_LOSE)
            self.strike(a_unit, b_unit, a_skill, a_ctx, carried=a_kept)
            # Unbreakable Coin：失败方的 Cracked 硬币仍会结算
            if b_cracked and b_unit.alive:
                self.log("cracked_coins", {"unit": b_unit.uid, "skill": b_skill.sid,
                                           "coins": sorted(b_cracked)})
                self.strike(b_unit, a_unit, b_skill, b_ctx, carried=b_cracked,
                            cracked=set(b_cracked))
        elif winner == "b":
            before = b_unit.sp
            if b_unit.has_sanity:
                b_unit.sp = min(b_unit.max_sp, b_unit.sp + self.config.clash_win_sp_gain)
            if a_unit.has_sanity:
                a_unit.sp = max(-a_unit.max_sp, a_unit.sp + self.config.clash_lose_sp_loss)
            b_unit.state["clash_wins_this_turn"] = int(b_unit.state.get("clash_wins_this_turn", 0)) + 1
            self.log("clash_win", {"unit": b_unit.uid, "skill": b_skill.sid,
                                   "sp": b_unit.sp, "cracked": sorted(a_cracked)})
            self.log_sp(b_ctx, b_unit, before, b_unit.sp, {"kind": "clash_win"})
            b_ctx.clash_result = "win"
            a_ctx.clash_result = "lose"
            run_hooks(b_skill.effects, b_ctx, Timing.CLASH_WIN)
            run_hooks(a_skill.effects, a_ctx, Timing.CLASH_LOSE)
            self.strike(b_unit, a_unit, b_skill, b_ctx, carried=None)
            if a_cracked and a_unit.alive:
                self.log("cracked_coins", {"unit": a_unit.uid, "skill": a_skill.sid,
                                           "coins": sorted(a_cracked)})
                self.strike(a_unit, b_unit, a_skill, a_ctx, carried=a_cracked,
                            cracked=set(a_cracked))
        else:
            self.log("clash_draw", {"a": a_unit.uid, "b": b_unit.uid})

    def _clash_advance(self, a_unit: Unit, a_skill: Skill, b_unit: Unit, b_skill: Skill):
        """拼点模型 A：双方每轮各消耗自己的下一枚硬币（硬币数多者占优）。

        Unbreakable Coin：拼点失败时不破坏而是 **Cracked**（保留并在失败后仍能结算，
        威力固定 +1/−1）。
        """
        ai = bi = 0
        a_destroyed = b_destroyed = 0
        a_kept: dict = {}
        b_kept: dict = {}
        a_cracked: dict = {}
        b_cracked: dict = {}
        while ai < len(a_skill.coins) and bi < len(b_skill.coins):
            a_heads = self.flip(a_unit, a_skill.coins[ai])
            b_heads = self.flip(b_unit, b_skill.coins[bi])
            av = self.clash_value(a_unit, a_skill, ai, a_heads, opponent=b_unit)
            bv = self.clash_value(b_unit, b_skill, bi, b_heads, opponent=a_unit)
            self.log("clash_roll", {
                "a_coin": ai, "a_heads": a_heads, "a_power": av,
                "b_coin": bi, "b_heads": b_heads, "b_power": bv,
                "result": "a" if av > bv else ("b" if bv > av else "tie")})
            if av > bv:
                if b_skill.coins[bi].unbreakable:
                    b_cracked[bi] = b_heads
                else:
                    b_destroyed += 1
                a_kept[ai] = a_heads
            elif bv > av:
                if a_skill.coins[ai].unbreakable:
                    a_cracked[ai] = a_heads
                else:
                    a_destroyed += 1
                b_kept[bi] = b_heads
            else:
                if self.config.clash_tie_destroys_both:
                    if a_skill.coins[ai].unbreakable:
                        a_cracked[ai] = a_heads
                    else:
                        a_destroyed += 1
                    if b_skill.coins[bi].unbreakable:
                        b_cracked[bi] = b_heads
                    else:
                        b_destroyed += 1
                else:
                    a_kept[ai] = a_heads
                    b_kept[bi] = b_heads
            ai += 1
            bi += 1
        # 判负条件：自己的硬币**全部**被破坏或 Cracked（wiki：Unbreakable 只是不破坏）
        a_left = len(a_skill.coins) - a_destroyed - len(a_cracked)
        b_left = len(b_skill.coins) - b_destroyed - len(b_cracked)
        a_out = a_left <= 0
        b_out = b_left <= 0
        if a_out and not b_out:
            winner = "b"
        elif b_out and not a_out:
            winner = "a"
        elif a_out and b_out:
            winner = "a" if len(a_kept) > len(b_kept) else ("b" if len(b_kept) > len(a_kept) else "draw")
        else:
            winner = "a" if a_left > b_left else ("b" if b_left > a_left else "draw")
        self.bump("clash_count")
        kept = a_kept if self.config.clash_coin_carryover else None
        return winner, kept, a_cracked, b_cracked

    def _clash_reflex(self, a_unit: Unit, a_skill: Skill, b_unit: Unit, b_skill: Skill):
        """拼点模型 B（synthetic）：胜者保留当前硬币续拼，只有败者硬币被破坏。

        这个模型下「高威力少硬币」的技能在拼点中很强（更接近单硬币 E.G.O 的手感）。
        """
        ai = bi = 0
        while ai < len(a_skill.coins) and bi < len(b_skill.coins):
            a_heads = self.flip(a_unit, a_skill.coins[ai])
            b_heads = self.flip(b_unit, b_skill.coins[bi])
            av = self.clash_value(a_unit, a_skill, ai, a_heads, opponent=b_unit)
            bv = self.clash_value(b_unit, b_skill, bi, b_heads, opponent=a_unit)
            self.log("clash_roll", {
                "a_coin": ai, "a_heads": a_heads, "a_power": av,
                "b_coin": bi, "b_heads": b_heads, "b_power": bv,
                "result": "a" if av > bv else ("b" if bv > av else "tie")})
            if av > bv:
                bi += 1
            elif bv > av:
                ai += 1
            else:
                ai += 1
                bi += 1
        if bi >= len(b_skill.coins) and ai < len(a_skill.coins):
            winner = "a"
        elif ai >= len(a_skill.coins) and bi < len(b_skill.coins):
            winner = "b"
        else:
            winner = "draw"
        self.bump("clash_count")
        return winner, None

    def coin_power(self, unit: Unit, skill: Skill, coin_index: int, heads: bool,
                   cracked: bool = False, power_mod: int = 0) -> int:
        """Coin Roll = 硬币的 Final Power。

        * 常规：``base_power + (有利面时 coin.power)``；
        * **Cracked Unbreakable Coin**：Coin Power 固定为 +1（正面硬币）/ -1（负面硬币）；
        * 
          不会低于 0。
        """
        coin = skill.coins[coin_index]
        val = skill.base_power + power_mod
        if cracked:
            val += 1 if coin.kind.value == "positive" else -1
        elif coin.favorable(heads):
            val += coin.power
        return max(0, val)

    def _apply_coin_thresholds(self, actor: Unit, skill: Skill, coin_index: int) -> None:
        """HP 阈值 → 硬币转为 Unbreakable（真实 Imago 机制：<66% 最后一枚，<33% 全部）。"""
        for rule in skill.coin_thresholds or ():
            if not isinstance(rule, dict) or not rule.get("unbreakable"):
                continue
            if actor.hp_pct() > float(rule.get("below_pct", 0.0)):
                continue
            ref = rule.get("coin", "all")
            targets = range(len(skill.coins)) if ref == "all" else \
                [len(skill.coins) - 1 if ref == "last" else int(ref)]
            for i in targets:
                if 0 <= i < len(skill.coins):
                    skill.coins[i].unbreakable = True

    def clash_value(self, unit: Unit, skill: Skill, coin_index: int, heads: bool,
                    opponent: Optional[Unit] = None) -> int:
        """拼点威力。

        ``Battles`` 页：「The Skill with higher Level gains **1 Power per 3 Level difference,
        rounded down**」——因此需要对手的防御等级。
        """
        coin = skill.coins[coin_index]
        val = skill.base_power
        if coin.favorable(heads):
            val += coin.power
        for key, st in unit.statuses.items():
            spec = status_spec(key)
            if spec.clash_power_per_count:
                val += spec.clash_power_per_count * max(st.count, st.potency)
        if opponent is not None and self.config.clash_level_bonus_per_3:
            diff = unit.effective_offense_level(skill.offense_level_mod) - opponent.defense_level
            if diff > 0:
                val += int(diff // 3 * self.config.clash_level_bonus_per_3)
        val += int(unit.state.get("_clash_bonus", 0))
        return val

    # ------------------------------------------------------------------
    def strike(self, actor: Unit, target: Unit, skill: Skill, proto: Ctx,
               carried: Optional[dict] = None, first_index: int = 0,
               cracked: Optional[set] = None) -> None:
        """按硬币逐枚结算（含 Coin Reuse 与追加硬币）。

        Coin Reuse 的真实语义（wiki.gg/Battles + E.G.O 文本）：
        * 只重复**指定的那一枚**硬币；
        * ``max_reuse`` 是每技能上限；
        * 每次 reuse 前重新判定条件；
        * reuse 的硬币重新走完整结算（含 [On Hit]）。
        """
        if target is None or not target.alive:
            return
        carried = carried or {}
        cracked = cracked or set()
        run_hooks(skill.effects, proto, Timing.BEFORE_ATTACK)
        frame = proto.frame
        frame.setdefault("pending_reuse", [])
        frame.setdefault("reuse_counts", {})
        frame.setdefault("extra_queue", [])
        # synthetic 的「全硬币重复投掷」（需要显式 synthetic: true 才能触发）
        repeat_all = int(frame.get("repeat_all", 0))
        queue: list = []
        for ci in range(len(skill.coins)):
            queue.append(ci)
            for _ in range(repeat_all):
                queue.append(ci)
        for _ in range(int(proto.extra_coins)):
            if queue:
                queue.append(queue[-1])
        if cracked:
            queue = [ci for ci in queue if ci in cracked]
        proto.extra_coins = 0
        throw_counts: dict = {}
        extra_throws = repeat_all * len(skill.coins)
        i = 0
        while i < len(queue):
            ci = queue[i]
            i += 1
            if ci >= len(skill.coins):
                continue
            extra, ended = self._throw_coin(actor, target, skill, ci, proto, carried,
                                            throw_counts, is_reuse=False,
                                            cracked=ci in cracked)
            extra_throws += extra
            if ended:
                return
            # 处理本次投掷注册的 Coin Reuse 请求（reuse 抛掷可能再注册新的）
            guard = 0
            while frame["pending_reuse"] and guard < 256:
                guard += 1
                req = frame["pending_reuse"].pop(0)
                tci = int(req["coin"])
                if frame["reuse_counts"].get(tci, 0) >= int(req["max_reuse"]):
                    continue
                check_ctx = proto.clone_for_coin(tci, skill.coins[tci])
                if not eval_condition(req.get("if"), check_ctx):
                    continue
                frame["reuse_counts"][tci] = frame["reuse_counts"].get(tci, 0) + 1
                self.bump("reuse_count")
                extra, ended = self._throw_coin(actor, target, skill, tci, proto, None,
                                                throw_counts, is_reuse=True,
                                                cracked=tci in cracked)
                extra_throws += extra
                if ended:
                    return
            while frame["extra_queue"]:
                queue.append(frame["extra_queue"].pop(0))
        if extra_throws:
            self.bump("repeat_coin", extra_throws)
        run_hooks(skill.effects, proto, Timing.AFTER_ATTACK)

    def _throw_coin(self, actor: Unit, target: Unit, skill: Skill, ci: int, proto: Ctx,
                    carried: Optional[dict], throw_counts: dict,
                    is_reuse: bool = False, cracked: bool = False) -> tuple:
        """投掷一枚硬币（含 synthetic 的「本硬币再投一次」循环）。返回 (额外投掷数, 是否终止)。"""
        throw_index = throw_counts.get(ci, 0)
        throw_counts[ci] = throw_index + 1
        carry_heads = None
        if not is_reuse and throw_index == 0 and carried:
            carry_heads = carried.get(ci)
        repeats = 0
        extra = 0
        ctx = None
        while True:
            ctx = proto.clone_for_coin(ci, skill.coins[ci])
            ctx.is_reuse = is_reuse or repeats > 0
            ctx.cracked = cracked
            ctx.clash_count = int(actor.state.get("clash_wins_this_turn", 0))
            ctx.clash_result = proto.clash_result
            if carry_heads is not None and repeats == 0:
                heads = carry_heads
            else:
                heads = self.flip(actor, skill.coins[ci])
            ctx.coin_heads = heads
            self.resolve_coin(actor, target, skill, ci, ctx)
            if self.check_end():
                return extra, True
            if (ctx.repeat_extra > 0 and self.config.coin_reuse_enabled
                    and not ctx.is_reuse
                    and repeats < self.config.max_repeat_per_coin):
                ctx.repeat_extra -= 1
                repeats += 1
                extra += 1
                carry_heads = None
                continue
            break
        if ctx is not None and ctx.extra_coins > 0:
            n = int(ctx.extra_coins)
            ctx.extra_coins = 0
            proto.frame["extra_queue"].extend([ci] * n)
        return extra, False

    def resolve_coin(self, actor: Unit, target: Unit, skill: Skill, ci: int, ctx: Ctx) -> None:
        coin = skill.coins[ci]
        self._apply_coin_thresholds(actor, skill, ci)
        when_side = Timing.COIN_HEADS if ctx.coin_heads else Timing.COIN_TAILS
        hit_side = Timing.HEADS_HIT if ctx.coin_heads else Timing.TAILS_HIT
        run_hooks(coin.effects, ctx, Timing.COIN_START)
        run_hooks(skill.effects, ctx, Timing.COIN_START)
        run_hooks(coin.effects, ctx, Timing.BEFORE_COIN)
        run_hooks(skill.effects, ctx, Timing.BEFORE_COIN)
        run_hooks(coin.effects, ctx, when_side)
        run_hooks(skill.effects, ctx, when_side)
        self.log("coin", {
            "unit": actor.uid, "target": target.uid, "skill": skill.sid, "coin": ci,
            "heads": ctx.coin_heads, "coin_kind": coin.kind.value, "damage": coin.damage,
            "reuse": bool(ctx.is_reuse), "cracked": bool(ctx.cracked),
            "power": self.coin_power(actor, skill, ci, bool(ctx.coin_heads), cracked=ctx.cracked)})
        # [命中时]（本模拟器默认每枚硬币都会命中；闪避类机制不在本实验范围）
        run_hooks(coin.effects, ctx, hit_side)
        run_hooks(skill.effects, ctx, hit_side)
        run_hooks(coin.effects, ctx, Timing.COIN_HIT)
        run_hooks(skill.effects, ctx, Timing.COIN_HIT)
        if ctx.clash_result == "win":
            run_hooks(coin.effects, ctx, Timing.HIT_AFTER_CLASH_WIN)
            run_hooks(skill.effects, ctx, Timing.HIT_AFTER_CLASH_WIN)
        elif ctx.clash_result == "lose":
            run_hooks(coin.effects, ctx, Timing.HIT_AFTER_CLASH_LOSE)
            run_hooks(skill.effects, ctx, Timing.HIT_AFTER_CLASH_LOSE)
        if ctx.cracked:
            run_hooks(coin.effects, ctx, Timing.ON_HIT_WITHOUT_CRACKING)
            run_hooks(skill.effects, ctx, Timing.ON_HIT_WITHOUT_CRACKING)
        if not ctx.cancel_hit:
            coin_roll = self.coin_power(actor, skill, ci, bool(ctx.coin_heads), cracked=ctx.cracked)
            coin_roll += ctx.power_mod
            adder = coin.damage + ctx.damage_mod  # coin.damage = synthetic attack adder
            deal(self, actor, target, max(0, coin_roll), skill.sin, skill.damage_type,
                 ctx=ctx, origin="coin", offense_bonus=skill.offense_level_mod,
                 adder=adder)
        # 目标身上的「命中时」状态（沉沦 / 蝶 / 破裂…）
        if self.config.status_hooks_enabled:
            self.run_status_hooks(target, Timing.COIN_HIT,
                                  opponent=actor, skill=skill, ci=ci, coin_heads=ctx.coin_heads,
                                  damage=ctx.damage)
        # 攻击者自身的状态在命中时的触发
        self.run_status_hooks(actor, Timing.COIN_HIT,
                              opponent=target, skill=skill, ci=ci, coin_heads=ctx.coin_heads,
                              damage=ctx.damage)
        if actor.passive_effects:
            run_hooks(actor.passive_effects, ctx, Timing.COIN_HIT)
        run_hooks(coin.effects, ctx, Timing.AFTER_COIN)
        run_hooks(skill.effects, ctx, Timing.AFTER_COIN)

    def run_status_hooks(self, unit: Unit, when: Timing, opponent: Optional[Unit] = None,
                         skill: Optional[Skill] = None, ci: int = -1,
                         coin_heads: Optional[bool] = None, damage: int = 0,
                         coin=None) -> None:
        for key in sorted(unit.statuses):
            spec = status_spec(key)
            if not spec.hooks:
                continue
            hooks = [h for h in spec.hooks if isinstance(h, dict) and h.get("when") == when.value]
            if not hooks:
                continue
            ctx = Ctx(self, unit, opponent, skill, coin=coin, coin_index=ci,
                      coin_heads=coin_heads, damage=damage, source=f"status:{key}", when=when.value)
            for h in hooks:
                if key == "sinking" and not self.config.sinking_enabled:
                    continue
                if key == BUTTERFLY and not self.config.butterfly_special_sinking:
                    continue
                eff = {k: v for k, v in h.items() if k != "when"}
                if eval_condition(eff.get("if"), ctx):
                    apply_effects([eff], ctx)

    # ------------------------------------------------------------------
    def run_all_hooks(self, when: Timing) -> None:
        """全体单位在某个时点触发自身状态钩子与被动。"""
        for u in self.state.all_units():
            if not u.alive and when is not Timing.TURN_END:
                continue
            self.run_status_hooks(u, when)
            if u.passive_effects:
                ctx = Ctx(self, u, None, source="passive")
                run_hooks(u.passive_effects, ctx, when)

    # ------------------------------------------------------------------
    def end_turn(self) -> None:
        self.log("turn_end", {"turn": self.state.turn})
        self.run_all_hooks(Timing.TURN_END)
        # 状态自然衰减
        for u in self.state.all_units():
            for key in list(u.statuses):
                spec = status_spec(key)
                st = u.statuses[key]
                if spec.turn_end_count_decay:
                    st.count = max(0, st.count - spec.turn_end_count_decay)
                if spec.turn_end_potency_decay:
                    st.potency = max(0, st.potency - spec.turn_end_potency_decay)
                if st.is_empty():
                    del u.statuses[key]
        # 幻影：整回合没有被作为主要目标 -> 回补对应状态栈
        self.phantom_restore()
        self.change_form()
        self.state.flags.pop("targeted_phantoms", None)
        self.check_end()
        self.sync()
        # 计划书 §22：每个回合都要能给出「回合结束时的 state hash」
        self.log("turn_hash", {"hash": self.state.hash()})

    def phantom_restore(self) -> None:
        targeted = set(self.state.flags.get("targeted_phantoms") or [])
        for p in self.state.phantoms():
            if not p.alive:
                continue
            if p.uid in targeted:
                continue
            amount = self.config.phantom_restore_amount
            if amount == 0:
                continue
            self.add_stacks(amount, p.time_type or "all", None, reason="phantom_restore")
        if targeted or self.state.phantoms():
            self.log("phantom_restore_check", {"targeted": sorted(targeted)})

    # ==================================================================
    # 罗生蝶：状态栈 / 形态 / 阈值
    # ==================================================================
    def add_stacks(self, amount: int, time: str, ctx: Optional[Ctx], reason: str = "") -> None:
        boss = self.boss()
        if boss is None or not boss.alive:
            return
        if time in ("all", "", None):
            keys = [PAST, PRESENT, FUTURE]
        elif time == "highest":
            keys = [boss.state.get("form", Form.PRESENT.value)]
        elif time == "target_time":
            tgt = ctx.other_unit if ctx else None
            keys = [tgt.time_type] if tgt is not None and tgt.time_type else []
        elif time in (PAST, PRESENT, FUTURE):
            keys = [time]
        else:
            keys = [time]
        for k in keys:
            if amount >= 0:
                boss.add_status(k, count=amount)
            else:
                st = boss.statuses.get(k)
                if st is None:
                    continue
                st.count = max(0, st.count + amount)
                if st.is_empty():
                    del boss.statuses[k]
            self.bump("stack_decay" if amount < 0 else "stack_gain")
        if amount < 0:
            self.bump("phantom_stack_decay", -amount)
        self.log("stacks", {"amount": amount, "time": time, "reason": reason,
                            "boss": {k: boss.status_count(k) for k in (PAST, PRESENT, FUTURE)}})
        self.change_form()

    def current_form(self) -> str:
        boss = self.boss()
        if boss is None:
            return Form.NEUTRAL.value
        vals = {k: boss.status_count(k) for k in (PAST, PRESENT, FUTURE)}
        top = max(vals.values())
        if top <= 0:
            return Form.NEUTRAL.value
        cur = boss.state.get("form")
        # 并列时保持当前形态，避免每回合无意义地反复切换
        if cur in vals and vals[cur] == top:
            return cur
        for k in (PAST, PRESENT, FUTURE):
            if vals[k] == top:
                return k
        return Form.NEUTRAL.value

    def change_form(self, force: Optional[str] = None) -> None:
        boss = self.boss()
        if boss is None or not boss.alive:
            return
        new = force or self.current_form()
        old = boss.state.get("form", Form.NEUTRAL.value)
        if new == old:
            return
        boss.state["form"] = new
        self.bump("form_switch")
        self.log("form_change", {"from": old, "to": new,
                                 "stacks": {k: boss.status_count(k)
                                            for k in (PAST, PRESENT, FUTURE)}})
        if self.config.form_switch_timegap:
            boss.add_status(TIMEGAP, count=self.config.form_switch_timegap)
            self.log("status", {"unit": boss.uid, "status": TIMEGAP,
                                "potency": 0, "count": self.config.form_switch_timegap,
                                "total_potency": boss.status_potency(TIMEGAP),
                                "total_count": boss.status_count(TIMEGAP),
                                "source": "form_change", "by": ""})
        ctx = Ctx(self, boss, None, source="form_change")
        run_hooks(boss.passive_effects, ctx, Timing.ON_FORM_CHANGE)
        if boss.state.get("on_form_change_effects"):
            run_hooks(boss.state["on_form_change_effects"], ctx, Timing.ON_FORM_CHANGE)

    def activate_time_state(self) -> None:
        """Moment of Entangled Lives（wiki.gg/Imago passive）：

        回合开始激活三套时间栈中最高的一个；并列时保持当前激活状态；
        激活状态改变时获得 1 层 Temporal Disjunction（效果未实现，只记录）。
        """
        boss = self.boss()
        if boss is None or not boss.alive:
            return
        keys = (IN_THE_PAST, IN_THE_PRESENT, IN_THE_FUTURE)
        stacks = {k: boss.status_count(k) for k in keys}
        top = max(stacks.values())
        if top <= 0:
            return
        cur = boss.state.get("active_time_state")
        if cur in stacks and stacks[cur] == top:
            new = cur
        else:
            new = next(k for k in keys if stacks[k] == top)
        if new != cur:
            boss.state["active_time_state"] = new
            self.bump("time_state_changes")
            self.log("time_state_change", {"from": cur, "to": new, "stacks": stacks})
        boss.state["cycle_turn"] = int(boss.state.get("cycle_turn", 0)) + 1

    def check_hp_thresholds(self, unit: Unit) -> None:
        thresholds = unit.state.get("stack_thresholds") or []
        idx = int(unit.state.get("stack_threshold_index", 0))
        while idx < len(thresholds) and unit.hp <= thresholds[idx]:
            idx += 1
            unit.state["stack_threshold_index"] = idx
            self.log("hp_threshold", {"unit": unit.uid, "threshold": thresholds[idx - 1],
                                      "hp": unit.hp})
            if unit.kind == "boss" and self.config.hp_threshold_stack_bonus:
                self.add_stacks(self.config.hp_threshold_stack_bonus, "all", None,
                                reason="hp_threshold")
            ctx = Ctx(self, unit, None, source="hp_threshold")
            run_hooks(unit.passive_effects, ctx, Timing.ON_HP_THRESHOLD)
            ctx.note["threshold_index"] = idx
            if unit.state.get("on_hp_threshold_effects"):
                apply_effects(unit.state["on_hp_threshold_effects"], ctx)

    # ==================================================================
    # 伤害 / 混乱 / 死亡
    # ==================================================================
    def apply_damage(self, source: Optional[Unit], target: Unit, amount: int,
                     bd: Optional[DamageBreakdown], origin: str = "skill") -> int:
        """伤害结算 + 混乱 / 死亡 / 本体阈值。"""
        if target is None or not target.alive or amount <= 0:
            return 0
        absorbed = 0
        if target.shield > 0 and amount > 0:
            absorbed = min(target.shield, amount)
            target.shield -= absorbed
            amount -= absorbed
            self.log("shield", {"unit": target.uid, "absorbed": absorbed, "shield": target.shield})
        if amount > 0:
            target.hp -= amount
        self.bump("total_damage", amount)
        self.log("damage", {"source": source.uid if source else "", "target": target.uid,
                            "amount": amount, "origin": origin, "hp": max(0, target.hp),
                            "breakdown": bd.to_dict() if bd else None})
        # 幻影伤害转移给本体
        if target.kind == "phantom":
            if self.config.phantom_stack_decay_per_coin and origin == "coin":
                # Moment of Entangled Lives：幻影被作为主要目标攻击时，本体失去对应栈
                self.add_stacks(-self.config.phantom_stack_decay_per_coin, target.time_type or "all",
                                None, reason="illusory_butterfly_hit")
            if self.config.phantom_damage_transfer > 0:
                boss = self.boss()
                transfer = int(round(amount * self.config.phantom_damage_transfer))
                if boss is not None and boss.alive and transfer > 0:
                    self.log("transfer", {"from": target.uid, "to": boss.uid, "amount": transfer})
                    self.apply_damage(source, boss, transfer, bd, origin="transfer")
        self.check_stagger(target)
        self.check_hp_thresholds(target)
        self.check_death(target)
        return amount + absorbed

    def check_stagger(self, unit: Unit) -> None:
        thresholds = unit.stagger_thresholds or []
        staggered_now = False
        while unit.stagger_index < len(thresholds) and unit.hp <= thresholds[unit.stagger_index]:
            unit.stagger_index += 1
            staggered_now = True
        if staggered_now:
            self.force_stagger(unit)

    def force_stagger(self, unit: Unit) -> None:
        unit.staggered = True
        # 同回合跨过多个阈值 → 混乱等级上升（Stagger/+/++ = +1 / +1.5 / +2 静态修正）
        unit.stagger_level = min(3, unit.stagger_level + 1)
        unit.state["stagger_until_turn"] = (self.state.turn + 1
                                            if self.config.stagger_lasts_next_turn
                                            else self.state.turn)
        for s in unit.slots:
            if not s.acted:
                s.cancelled = True
        self.bump("stagger_count")
        self.log("stagger", {"unit": unit.uid, "hp": unit.hp,
                             "threshold_index": unit.stagger_index})
        ctx = Ctx(self, unit, None, source="stagger")
        self.run_status_hooks(unit, Timing.ON_STAGGER)
        run_hooks(unit.passive_effects, ctx, Timing.ON_STAGGER)

    def check_death(self, unit: Unit) -> None:
        if unit.hp > 0 or not unit.alive:
            return
        unit.hp = 0
        unit.alive = False
        unit.staggered = False
        for s in unit.slots:
            s.cancelled = True
        self.bump("deaths")
        self.log("death", {"unit": unit.uid, "kind": unit.kind})
        ctx = Ctx(self, unit, None, source="death")
        run_hooks(unit.passive_effects, ctx, Timing.ON_DEATH)
        if unit.side is Side.ALLY:
            for other in self.state.allies:
                if other.alive:
                    before = other.sp
                    other.sp = max(-other.max_sp, other.sp + self.config.ally_death_sp_loss)
                    self.log_sp(ctx, other, before, other.sp, {"kind": "ally_death"})
        if unit.kind == "phantom":
            unit.state["revive_turn"] = self.state.turn + self.config.phantom_broken_turns
            self.log("phantom_broken", {"unit": unit.uid,
                                        "revive_turn": unit.state["revive_turn"]})

    # ==================================================================
    # 胜负
    # ==================================================================
    def check_end(self) -> bool:
        st = self.state
        if st.phase is Phase.TERMINAL:
            return True
        boss = self.boss()
        if boss is not None and not boss.alive:
            st.phase = Phase.TERMINAL
            st.outcome = Outcome.ALLY_WIN
            st.terminal = {"reason": "boss_down", "kill_turn": st.turn,
                           "total_damage": st.counters.get("total_damage", 0)}
            self.log("terminal", st.terminal)
            return True
        if not any(a.alive for a in st.allies):
            st.phase = Phase.TERMINAL
            st.outcome = Outcome.ALLY_LOSE
            st.terminal = {"reason": "all_allies_down", "turn": st.turn}
            self.log("terminal", st.terminal)
            return True
        if st.turn >= self.config.max_turns:
            st.phase = Phase.TERMINAL
            st.outcome = Outcome.ALLY_LOSE
            st.terminal = {"reason": "turn_limit", "turn": st.turn}
            self.log("terminal", st.terminal)
            return True
        return False

    # ==================================================================
    # 随机
    # ==================================================================
    def flip(self, unit: Unit, coin) -> bool:
        """翻一枚硬币，返回是否正面。所有随机性都走这里。"""
        mode = self.config.coin_mode
        if mode == "always_heads":
            return True
        if mode == "always_tails":
            return False
        if mode == "script":
            script = self.config.coin_script
            if not script:
                return True
            v = script[self.state.script_pos % len(script)]
            self.state.script_pos += 1
            return bool(v) if isinstance(v, bool) else str(v).lower() in ("heads", "h", "1", "true")
        if not getattr(unit, "has_sanity", True):
            # 无 SP 单位（Abnormality）：固定 50%（计划书/审计 §3）
            p = 0.5
        else:
            p = heads_probability(unit.sp, self.config.san_per_point)
        return self.rng.chance(p)
