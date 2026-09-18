"""rr6sim：RR6 罗生蝶「沉沦 + 重骰 E.G.O」策略涌现实验的模拟器内核。

模块划分（对应计划书 §5.2 的 crates 划分，这里用 Python 包实现）：

* ``rr6sim.core``    —— 纯规则引擎（事件时点、拼点、逐硬币结算、状态）
* ``rr6sim.content`` —— 数据加载与内容注册（data/*.json）
* ``rr6sim.env``     —— 自回归动作空间、观察、Gymnasium 风格环境
* ``rr6sim.search``  —— 搜索基线（greedy / beam）
* ``rr6sim.replay``  —— replay 导出与验证
"""

from .core.config import SimConfig
from .content.loader import Content
from .env.rr6_env import RR6ButterflyEnv
from .simulate import apply_plan, new_battle, simulate_plan

__all__ = [
    "SimConfig",
    "Content",
    "RR6ButterflyEnv",
    "new_battle",
    "apply_plan",
    "simulate_plan",
]
