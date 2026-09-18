"""伤害计算：按 wiki.gg 的真实公式实现（docs/audit_report.md §2）。

真实公式（``Damage Formula`` 页）：

    Final Damage = Coin Roll × (1 + Static Modifiers) × (1 + Dynamic Modifiers)

* **Coin Roll = 该硬币的 Final Power**（不是技能数据里独立的 ``coin damage``）。
* ``Final damage`` 向下取整，且不低于 1；若低于 ``0.05 × Coin Roll`` 则取 ``0.05 × Coin Roll``。
* ``Static Modifiers`` =
  ``Sin Res Mod + Damage Res Mod + Off/Def Level Advantage + Crit + Clash Count × 0.03 + Observation Level``
* 抗性是分段函数（不是乘法）：

      x < 0      → -0.5        # Immune 实际是吃一半伤害
      0 ≤ x < 1  → (x-1)/2     # Ineff. x0.5 实际 -25%
      x ≥ 1      → x-1         # Weak x1.5 → +50%，Fatal x2 → +100%

* 攻防等级：``M = (Off - Def) / (|Off - Def| + 25)``
* 混乱：该回合把**物理抗性**替换为 ``Stagger Level × 0.5 + 0.5``
  （Stagger/+/++ = +1 / +1.5 / +2），与原有弱点取较高者。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .enums import DamageType, Sin
from .unit import Unit


def resistance_modifier(x: float) -> float:
    """抗性 → 静态修正（分段函数）。"""
    if x < 0:
        return -0.5
    if x < 1:
        return (x - 1.0) / 2.0
    return x - 1.0


def offense_defense_modifier(offense: int, defense: int) -> float:
    """攻防等级差 → 静态修正。"""
    diff = offense - defense
    if diff == 0:
        return 0.0
    return diff / (abs(diff) + 25.0)


@dataclass
class DamageBreakdown:
    coin_roll: int = 0
    static: float = 0.0
    dynamic: float = 0.0
    amount: int = 0
    # 明细
    sin_res_mod: float = 0.0
    dtype_res_mod: float = 0.0
    level_mod: float = 0.0
    clash_count_mod: float = 0.0
    stagger_level: int = 0
    status_dynamic: float = 0.0
    skill_dynamic: float = 1.0
    adder: int = 0
    sin: str = ""
    damage_type: str = ""
    target: str = ""
    offense: int = 0
    defense: int = 0

    def to_dict(self) -> dict:
        return {
            "coin_roll": self.coin_roll,
            "static": round(self.static, 4),
            "dynamic": round(self.dynamic, 4),
            "amount": self.amount,
            "sin_res_mod": round(self.sin_res_mod, 4),
            "dtype_res_mod": round(self.dtype_res_mod, 4),
            "level_mod": round(self.level_mod, 4),
            "clash_count_mod": round(self.clash_count_mod, 4),
            "stagger_level": self.stagger_level,
            "status_dynamic": round(self.status_dynamic, 4),
            "skill_dynamic": round(self.skill_dynamic, 4),
            "adder": self.adder,
            "sin": self.sin,
            "damage_type": self.damage_type,
            "target": self.target,
            "offense": self.offense,
            "defense": self.defense,
        }

    def summary(self) -> str:
        return (f"{self.amount} = coin_roll {self.coin_roll} "
                f"× (1{self.static:+.3f}) × (1{self.dynamic:+.3f})")


def compute_damage(
    battle,
    source: Optional[Unit],
    target: Unit,
    coin_roll: int,
    sin: Sin,
    damage_type: DamageType,
    offense_bonus: int = 0,
    temp_mult: float = 1.0,
    adder: int = 0,
    clash_count: int = 0,
) -> DamageBreakdown:
    """按真实公式计算一次硬币命中伤害。

    ``temp_mult`` 是技能条件类的**动态修正**（例如「造成 +X% 伤害」），
    按动态修正的加法口径折算成 ``(1 + x)``。
    """
    cfg = battle.config
    bd = DamageBreakdown(coin_roll=max(0, int(coin_roll)),
                         sin=sin.value, damage_type=damage_type.value, target=target.uid)
    if coin_roll <= 0:
        return bd

    # ---- 静态修正 ----
    sin_res = target.resistance_value(sin)
    dtype_res = target.resistance_value_type(damage_type)
    bd.sin_res_mod = resistance_modifier(sin_res)
    if target.staggered and target.stagger_level > 0:
        # 混乱时物理抗性被替换为 (0.5 + 0.5 × 等级)，与已有弱点取较高者
        stagger_mod = target.stagger_level * 0.5 + 0.5
        bd.dtype_res_mod = max(stagger_mod, resistance_modifier(dtype_res))
    else:
        bd.dtype_res_mod = resistance_modifier(dtype_res)
    if source is not None:
        bd.offense = source.effective_offense_level(offense_bonus)
    else:
        bd.offense = 50
    bd.defense = target.defense_level
    bd.level_mod = offense_defense_modifier(bd.offense, bd.defense)
    bd.clash_count_mod = 0.03 * clash_count
    static = (bd.sin_res_mod + bd.dtype_res_mod + bd.level_mod
              + bd.clash_count_mod + cfg.observation_level_modifier)
    bd.static = static

    # ---- 动态修正 ----
    status_dyn = target.dynamic_damage_taken() + (source.dynamic_damage_dealt() if source else 0.0)
    bd.status_dynamic = status_dyn
    bd.skill_dynamic = temp_mult
    dynamic = status_dyn + (temp_mult - 1.0)
    bd.dynamic = dynamic

    raw = coin_roll * (1.0 + static) * (1.0 + dynamic) + adder
    bd.adder = adder
    final = int(math.floor(raw))
    if final < 1:
        final = 1
    minimum = 0.05 * coin_roll
    if final < minimum:
        final = int(math.ceil(minimum))
    bd.amount = max(0, final)
    return bd


def deal(
    battle,
    source: Optional[Unit],
    target: Unit,
    coin_roll: int,
    sin: Sin,
    damage_type: DamageType,
    ctx=None,
    origin: str = "skill",
    offense_bonus: int = 0,
    adder: int = 0,
    flat: bool = False,
) -> int:
    """结算一次伤害，返回实际扣除的 HP。

    ``flat=True`` 表示「固定伤害」/状态伤害（例如 Sinking 对无 SP 单位的 Gloom 伤害）：
    这种伤害**忽略物理伤害类型抗性与等级修正**，只受罪孽抗性影响
    （wiki.gg/Sinking：「damage caused by Sinking will ignore Damage Type resistances,
    but not Sin resistances」）。
    """
    if target is None or not target.alive:
        return 0
    if flat:
        sin_res = target.resistance_value(sin)
        mult = 1.0 + resistance_modifier(sin_res)
        amount = max(1, int(math.floor(coin_roll * mult))) if coin_roll > 0 else 0
        bd = DamageBreakdown(coin_roll=int(coin_roll), amount=amount, sin=sin.value,
                             damage_type=damage_type.value, target=target.uid,
                             sin_res_mod=resistance_modifier(sin_res), static=mult - 1.0)
        if ctx is not None:
            ctx.damage = amount
        return battle.apply_damage(source, target, amount, bd, origin=origin)

    temp_mult = getattr(ctx, "damage_mult", 1.0) if ctx is not None else 1.0
    flat_mod = getattr(ctx, "damage_mod", 0) if ctx is not None else 0
    bd = compute_damage(battle, source, target, coin_roll, sin, damage_type,
                        offense_bonus=offense_bonus, temp_mult=temp_mult,
                        adder=adder + flat_mod,
                        clash_count=getattr(ctx, "clash_count", 0) if ctx is not None else 0)
    if ctx is not None:
        ctx.damage = bd.amount
    return battle.apply_damage(source, target, bd.amount, bd, origin=origin)
