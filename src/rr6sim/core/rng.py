"""确定性随机数。

计划书 §10 要求所有随机性都能被 seed 复现、被 replay 审计。
这里用 SplitMix64：状态就是一个 u64 整数，天然可序列化、可回滚、可 hash。
（Python 自带 ``random`` 的状态是 Mersenne Twister 的大块状态，序列化不友好，
所以自己实现一个。）

注意：**不要把 rng_state 暴露给策略网络**（计划书 §13）。
"""

from __future__ import annotations

MASK64 = (1 << 64) - 1
GOLDEN = 0x9E3779B97F4A7C15


class SplitMix64:
    """可复现、可回滚的 PRNG。

    >>> r = SplitMix64(1); a = r.next_u64(); r2 = SplitMix64(1); a == r2.next_u64()
    True
    """

    __slots__ = ("state",)

    def __init__(self, seed: int = 0) -> None:
        self.state = seed & MASK64

    def next_u64(self) -> int:
        self.state = (self.state + GOLDEN) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)

    def random(self) -> float:
        """[0, 1) 均匀分布。"""
        return self.next_u64() / float(1 << 64)

    def chance(self, p: float) -> bool:
        if p <= 0.0:
            return False
        if p >= 1.0:
            return True
        return self.random() < p

    def randint(self, lo: int, hi: int) -> int:
        """闭区间整数 [lo, hi]。"""
        if hi <= lo:
            return lo
        return lo + int(self.next_u64() % (hi - lo + 1))

    def choice(self, seq):
        return seq[self.randint(0, len(seq) - 1)]

    def snapshot(self) -> int:
        return self.state

    def restore(self, state: int) -> None:
        self.state = state & MASK64


def heads_probability(sanity: int, per_point: float = 0.01, lo: float = 0.05, hi: float = 0.95) -> float:
    """硬币正面的概率。

    计划书 §9.3：理智影响硬币正反概率。本实验采用社区通用近似
    ``P(正面) = 0.5 + SP * per_point``，并夹在 [lo, hi]。
    SP=45 -> 0.95，SP=-45 -> 0.05，SP=0 -> 0.5。
    正、负硬币共用同一公式：负硬币在低 SP 时更容易出反面（从而吃满硬币威力），
    这正是“泪锋之剑 / 绝望”类负硬币人格的设计逻辑。
    """
    p = 0.5 + sanity * per_point
    return max(lo, min(hi, p))
