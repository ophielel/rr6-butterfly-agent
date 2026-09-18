"""效果执行上下文。

技能效果、状态钩子、被动效果都通过同一个 ``Ctx`` 执行，这样
「谁对谁、哪一枚硬币、第几次触发」的信息在每一层都保持一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .enums import TargetMode
from .skill import Coin, Skill
from .unit import Unit


@dataclass
class Ctx:
    battle: Any
    self_unit: Unit
    other_unit: Optional[Unit] = None
    skill: Optional[Skill] = None
    coin: Optional[Coin] = None
    coin_index: int = -1
    coin_heads: Optional[bool] = None
    hit: bool = True
    cancel_hit: bool = False
    damage: int = 0
    source: str = "skill"
    when: str = ""
    mode: TargetMode = TargetMode.ONE_SIDED
    #: 每枚硬币的可变状态
    repeat_extra: int = 0       # 当前硬币还需重复投掷的次数
    is_repeat_throw: bool = False  # 本次投掷是否由「重复投掷」产生
    extra_coins: int = 0        # 攻击结束后追加的硬币数
    power_mod: int = 0          # 本次拼点威力修正
    damage_mod: int = 0
    damage_mult: float = 1.0
    note: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    def clone_for_coin(self, coin_index: int, coin: Coin) -> "Ctx":
        """为下一枚硬币派生一个干净的上下文（保留技能级修正）。"""
        return Ctx(
            battle=self.battle,
            self_unit=self.self_unit,
            other_unit=self.other_unit,
            skill=self.skill,
            coin=coin,
            coin_index=coin_index,
            source=self.source,
            when=self.when,
            mode=self.mode,
            power_mod=self.power_mod,
            damage_mod=self.damage_mod,
            damage_mult=self.damage_mult,
        )

    def owner(self, who: str = "self") -> Optional[Unit]:
        """按 who 取单位；状态钩子里 self = 状态持有者。"""
        if who in ("self", "owner", "actor"):
            return self.self_unit
        if who in ("other", "target", "attacker"):
            return self.other_unit
        return None

    def targets(self, token: str) -> list:
        """把数据文件里的目标 token 解析成单位列表。"""
        b = self.battle
        me = self.self_unit
        other = self.other_unit
        if token in ("self", "", None):
            return [me] if me else []
        if token in ("other", "target"):
            return [other] if other else []
        if token == "target_allies":
            if other is None:
                return []
            return [u for u in b.units_of(other.side) if u.alive]
        if token == "all_allies":
            return [u for u in b.units_of(me.side) if u.alive]
        if token == "all_enemies":
            return [u for u in b.units_of(_opposite(me.side)) if u.alive]
        if token == "boss":
            u = b.unit("boss")
            return [u] if u and u.alive else []
        if token.startswith("phantom:"):
            u = b.unit("phantom_" + token.split(":", 1)[1])
            return [u] if u and u.alive else []
        if token == "random_ally":
            pool = [u for u in b.units_of(me.side) if u.alive]
            return [b.rng.choice(pool)] if pool else []
        if token == "random_enemy":
            pool = [u for u in b.units_of(_opposite(me.side)) if u.alive]
            return [b.rng.choice(pool)] if pool else []
        if token == "lowest_hp_ally":
            pool = [u for u in b.units_of(me.side) if u.alive]
            return [min(pool, key=lambda u: u.hp)] if pool else []
        raise KeyError(f"未知目标 token: {token}")


def _opposite(side):
    from .enums import Side

    return Side.ENEMY if side is Side.ALLY else Side.ALLY
