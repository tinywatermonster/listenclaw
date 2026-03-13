from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
_EXAMPLE_CONFIG_PATH = Path(__file__).parent.parent / "config.example.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    # Start from example defaults
    with open(_EXAMPLE_CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    # Overlay user config if present
    target = Path(path) if path else _DEFAULT_CONFIG_PATH
    if target.exists():
        with open(target) as f:
            user = yaml.safe_load(f) or {}
        config = _deep_merge(config, user)

    return config


def get(config: dict, *keys: str, default: Any = None) -> Any:
    cur = config
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur
