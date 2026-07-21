from prompt_architect.adapters.base import ModelAdapter
from prompt_architect.schemas import AdapterGuidance, TargetAgent, TaskSpec


class ImageModelAdapter(ModelAdapter):
    target = TargetAgent.IMAGE_MODEL
    profile_key = "image_model"

    def guidance(self, task: TaskSpec) -> AdapterGuidance:
        return self._profile_guidance(task)
