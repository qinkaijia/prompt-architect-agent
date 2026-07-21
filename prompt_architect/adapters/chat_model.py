from prompt_architect.adapters.base import ModelAdapter
from prompt_architect.schemas import AdapterGuidance, TargetAgent, TaskSpec


class ChatModelAdapter(ModelAdapter):
    target = TargetAgent.CHAT_MODEL
    profile_key = "chat_model"

    def guidance(self, task: TaskSpec) -> AdapterGuidance:
        return self._profile_guidance(task)
