"""Gymnasium 风格环境（计划书 §11 / §12）。

动作空间 **不是**一个巨大的离散编号，而是自回归构造本回合计划：

    选择第 k 个我方行动槽
      -> 选择使用哪个技能 / 守备 / E.G.O（觉醒或侵蚀）
      -> 选择目标（敌方单位 + 敌方行动槽）
    重复直到本回合计划完成
      -> 结算整回合

每个决策点都提供合法的候选列表（列表下标就是离散动作编号），
资源不足 / E.G.O 不合法 / 目标不合法会直接被屏蔽掉。
"""

from __future__ import annotations

from typing import Optional

from ..core.config import SimConfig
from ..core.engine import Battle
from ..core.enums import Outcome, Phase, SlotKind
from ..content.loader import Content
from ..simulate import new_battle
from .obs import build_observation, summarize


class RR6ButterflyEnv:
    def __init__(self, config: Optional[SimConfig] = None, content: Optional[Content] = None,
                 seed: int = 0) -> None:
        self.config = (config or SimConfig()).normalized()
        self.content = content or Content()
        self.seed = seed
        self.battle: Battle = new_battle(self.content, self.config, seed)
        self._phase = "action"      # action | target
        self._slot = None
        self._last_info: dict = {}
        self._sync_phase()

    # ==================================================================
    # 生命周期
    # ==================================================================
    def reset(self, seed: Optional[int] = None) -> list:
        if seed is not None:
            self.seed = seed
        self.battle = new_battle(self.content, self.config, self.seed)
        self._phase = "action"
        self._slot = None
        self._last_info = {}
        self._sync_phase()
        return self.observation()

    def _sync_phase(self) -> None:
        if self._phase == "target" and self._slot is not None:
            return
        self._slot = self.battle.pending_slot()
        self._phase = "action"

    # ==================================================================
    # 决策点
    # ==================================================================
    def _owner_uid(self, slot) -> str:
        for u in self.battle.state.all_units():
            for s in u.slots:
                if s is slot:
                    return u.uid
        return ""

    def legal_actions(self) -> list:
        """当前决策点的合法动作列表（含人类可读标签）。"""
        if self.battle.state.phase is Phase.TERMINAL:
            return []
        slot = self._slot
        if slot is None:
            self._sync_phase()
            slot = self._slot
            if slot is None:
                return []
        owner = self._owner_uid(slot)
        if self._phase == "action":
            out = []
            for a in self.battle.legal_actions(slot):
                d = dict(a)
                d.update({"owner": owner, "slot": slot.index})
                d["label"] = self._label_action(d, slot)
                out.append(d)
            return out
        out = []
        for t in self.battle.legal_targets(slot):
            d = dict(t)
            d.update({"owner": owner, "slot": slot.index, "kind": "target"})
            d["label"] = f"{t['uid']}#{t['slot']}" + ("(拼点)" if t.get("clash") else
                                                      ("(改目标)" if t.get("redirect") else ""))
            if not t.get("clash") and not t.get("redirect"):
                d["label"] += "(单方面)"
            out.append(d)
        return out

    def _label_action(self, d: dict, slot) -> str:
        if d["kind"] == "guard":
            return "守备"
        if d["kind"] == "ego":
            ego = self.content.ego(d["id"])
            cost = ego.corrosion_sp_cost if d.get("corrosion") else ego.sp_cost
            suffix = "（侵蚀）" if d.get("corrosion") else ""
            return f"E.G.O {ego.name}{suffix} (SP{cost})"
        sk = self.content.skill(d["id"])
        return f"{sk.name} [{sk.sin.value}/{sk.damage_type.value}] {sk.coin_count}硬币"

    def legal_action_mask(self) -> list:
        return [True] * len(self.legal_actions())

    # ==================================================================
    # 推进
    # ==================================================================
    def step(self, action):
        """``action`` 可以是合法动作列表的下标，或动作 dict 本身。"""
        if self.battle.state.phase is Phase.TERMINAL:
            raise RuntimeError("战斗已结束，请先 reset()")
        legal = self.legal_actions()
        if not legal:
            # 计划已完成 -> 结算
            return self._resolve_turn()
        invalid = False
        if isinstance(action, int):
            if action < 0 or action >= len(legal):
                invalid = True
                choice = legal[0]
            else:
                choice = legal[action]
        else:
            choice = action
            if choice not in legal:
                invalid = True

        if self._phase == "action":
            self.battle.assign_action(self._slot, choice["kind"], choice["id"], choice.get("corrosion", False))
            if choice["kind"] == "guard":
                self.battle.assign_target(self._slot, "", -1)
                self._phase = "action"
                self._slot = None
                self._sync_phase()
            else:
                self._phase = "target"
        else:
            self.battle.assign_target(self._slot, choice["uid"], int(choice["slot"]))
            self._phase = "action"
            self._slot = None
            self._sync_phase()

        if self.battle.plan_complete():
            return self._resolve_turn(invalid=invalid)
        return self.observation(), 0.0, False, False, {"invalid": invalid, "phase": self._phase}

    def step_plan(self, plan: list):
        """直接提交一整回合的计划（给 Greedy / Beam / MCTS 用）。"""
        from ..simulate import apply_plan

        apply_plan(self.battle, plan)
        return self._resolve_turn()

    # ------------------------------------------------------------------
    def _resolve_turn(self, invalid: bool = False) -> tuple:
        b = self.battle
        boss_hp_before = b.boss().hp if b.boss() else 0
        b.resolve_turn()
        reward = self.config.reward_turn_penalty
        if self.config.reward_hp_shaping and b.boss() is not None:
            reward += self.config.reward_hp_shaping * (boss_hp_before - b.boss().hp)
        terminated = False
        truncated = False
        if b.state.phase is Phase.TERMINAL:
            reason = b.state.terminal.get("reason")
            if b.state.outcome is Outcome.ALLY_WIN:
                reward += self.config.reward_kill
                terminated = True
            elif reason == "turn_limit":
                truncated = True
            else:
                reward += self.config.reward_defeat
                terminated = True
        else:
            b.begin_turn()
            self._phase = "action"
            self._slot = None
            self._sync_phase()
            if b.plan_complete():
                # 极端情况：我方已无可用槽位，直接进入结算
                return self._resolve_turn()
        info = {
            "turn": b.state.turn,
            "outcome": b.state.outcome.value,
            "terminal": dict(b.state.terminal),
            "counters": dict(b.state.counters),
            "summary": summarize(b),
            "invalid": invalid,
        }
        self._last_info = info
        return self.observation(), reward, terminated, truncated, info

    # ==================================================================
    # 观察 / replay
    # ==================================================================
    def observation(self) -> list:
        vals, _ = build_observation(self.battle)
        return vals

    def observation_names(self) -> list:
        _, names = build_observation(self.battle)
        return names

    @property
    def observation_size(self) -> int:
        return len(self.observation())

    def export_replay(self) -> dict:
        from ..replay import export_replay

        return export_replay(self.battle)

    def clone_state(self):
        return self.battle.state.copy()

    def state_hash(self) -> str:
        return self.battle.state.hash()
