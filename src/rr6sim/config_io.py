"""配置文件读写（YAML / JSON）。

数据文件（``data/*.json``）与实验配置（``configs/*.yaml``）分开：
前者是「这个世界长什么样」，后者是「这次实验用什么规则」。
"""

from __future__ import annotations

import json
import os

from .core.config import SimConfig


def load_config(path: str) -> SimConfig:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("需要 pyyaml 才能读取 YAML 配置；也可以改用 JSON") from e
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return SimConfig.from_dict(data or {})


def save_config(cfg: SimConfig, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = cfg.to_dict()
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore

            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
            return path
        except ImportError:  # pragma: no cover
            pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path
