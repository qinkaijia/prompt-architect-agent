from prompt_architect.adapters.base import ModelAdapter
from prompt_architect.schemas import AdapterGuidance, TargetAgent, TaskSpec


class ClaudeCodeAdapter(ModelAdapter):
    target = TargetAgent.CLAUDE_CODE
    profile_key = "claude_code"

    def guidance(self, task: TaskSpec) -> AdapterGuidance:
        return self._profile_guidance(task)
