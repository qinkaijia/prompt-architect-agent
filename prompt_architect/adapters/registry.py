from __future__ import annotations

from prompt_architect.adapters.base import ModelAdapter
from prompt_architect.adapters.chat_model import ChatModelAdapter
from prompt_architect.adapters.claude_code import ClaudeCodeAdapter
from prompt_architect.adapters.codex import CodexAdapter
from prompt_architect.adapters.image_model import ImageModelAdapter
from prompt_architect.schemas import TargetAgent


class AdapterRegistry:
    def __init__(self, adapters: list[ModelAdapter] | None = None) -> None:
        instances = adapters or [CodexAdapter(), ClaudeCodeAdapter(), ChatModelAdapter(), ImageModelAdapter()]
        self._adapters = {adapter.target: adapter for adapter in instances}

    def get(self, target: TargetAgent) -> ModelAdapter:
        try:
            return self._adapters[target]
        except KeyError as exc:
            raise ValueError(f"No adapter registered for {target.value}") from exc
