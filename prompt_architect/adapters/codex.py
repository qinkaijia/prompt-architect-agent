from prompt_architect.adapters.base import ModelAdapter
from prompt_architect.schemas import AdapterGuidance, TargetAgent, TaskSpec


class CodexAdapter(ModelAdapter):
    target = TargetAgent.CODEX
    profile_key = "codex"

    def guidance(self, task: TaskSpec) -> AdapterGuidance:
        return self._profile_guidance(task)
