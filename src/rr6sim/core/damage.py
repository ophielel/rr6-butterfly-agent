"""伤害计算与结算。

公式结构（计划书 §9.5 / §9.6）：

    最终伤害 = 基础伤害
             × (1 + 攻击等级差 × level_diff_damage_per_level)
             × 物理抗性 × 罪孽抗性
             × 目标身上的「受到伤害倍率」（脆弱 / 时隙 / 混乱…）
             × 本次硬币的临时倍率

每一项都可以在 docs/mechanics_notes.md 里找到出处与「待校验」标记。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import DamageType, Sin
from .unit import Unit


@dataclass
class DamageBreakdown:
    amount: int
    level_diff: int = 0
    level_mult: float = 1.0
    resistance: float = 1.0
    status_mult: float = 1.0
    stagger_mult: float = 1.0
    guard_mult: float = 1.0
    temp_mult: float = 1.0
    sin: str = ""
    damage_type: str = ""
    target: str = ""

    def to_dict(self) -> dict:
        return {
            "amount": self.amount,
            "level_diff": self.level_diff,
            "level_mult": round(self.level_mult, 4),
            "resistance": round(self.resistance, 4),
            "status_mult": round(self.status_mult, 4),
            "stagger_mult": round(self.stagger_mult, 4),
            "guard_mult": round(self.guard_mult, 4),
            "temp_mult": round(self.temp_mult, 4),
            "sin": self.sin,
            "damage_type": self.damage_type,
            "target": self.target,
        }

    def summary(self) -> str:
        return (f"{self.amount} = {self.level_mult:.2f}x等级 * {self.resistance:.2f}x抗性 "
                f"* {self.status_mult:.2f}x状态 * {self.stagger_mult:.2f}x混乱")


def compute_damage(
    battle,
    source: Optional[Unit],
    target: Unit,
    amount: int,
    sin: Sin,
    damage_type: DamageType,
    offense_bonus: int = 0,
    temp_mult: float = 1.0,
) -> DamageBreakdown:
    cfg = battle.config
    bd = DamageBreakdown(amount=0, sin=sin.value, damage_type=damage_type.value, target=target.uid)
    if amount <= 0:
        return bd

    if source is not None:
        atk = source.effective_offense_level(offense_bonus)
        bd.level_diff = atk - target.defense_level
    bd.level_mult = max(0.05, 1.0 + cfg.level_diff_damage_per_level * bd.level_diff)
    bd.resistance = target.resistance(damage_type, sin)
    bd.status_mult = target.damage_taken_mult()
    bd.stagger_mult = cfg.stagger_damage_taken_mult if target.staggered else 1.0
    bd.guard_mult = cfg.guard_damage_mult if target.guard else 1.0
    bd.temp_mult = temp_mult * (source.damage_dealt_mult() if source is not None else 1.0)

    raw = (amount * bd.level_mult * bd.resistance * bd.status_mult
           * bd.stagger_mult * bd.guard_mult * bd.temp_mult)
    bd.amount = max(0, int(round(raw)))
    return bd


def deal(
    battle,
    source: Optional[Unit],
    target: Unit,
    amount: int,
    sin: Sin,
    damage_type: DamageType,
    ctx=None,
    origin: str = "skill",
    offense_bonus: int = 0,
) -> int:
    """结算一次伤害，返回实际扣除的 HP。

    幻影的伤害转移、混乱、死亡检查都在这里统一处理，避免各效果自己漏判。
    """
    if target is None or not target.alive:
        return 0
    temp_mult = getattr(ctx, "damage_mult", 1.0) if ctx is not None else 1.0
    flat_mod = getattr(ctx, "damage_mod", 0) if ctx is not None else 0

    bd = compute_damage(battle, source, target, amount + flat_mod, sin, damage_type,
                        offense_bonus=offense_bonus, temp_mult=temp_mult)
    if ctx is not None:
        ctx.damage = bd.amount

    actual = battle.apply_damage(source, target, bd.amount, bd, origin=origin)
    return actual
