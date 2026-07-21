from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml


@lru_cache(maxsize=None)
def load_config(filename: str) -> dict[str, Any]:
    resource = files("prompt_architect.config").joinpath(filename)
    with resource.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration {filename} must contain a mapping")
    return data
