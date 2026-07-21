from __future__ import annotations

from abc import ABC, abstractmethod

from prompt_architect.config_loader import load_config
from prompt_architect.schemas import AdapterGuidance, TargetAgent, TaskSpec


class ModelAdapter(ABC):
    target: TargetAgent
    profile_key: str

    @abstractmethod
    def guidance(self, task: TaskSpec) -> AdapterGuidance:
        raise NotImplementedError

    def _profile_guidance(self, task: TaskSpec) -> AdapterGuidance:
        profiles = load_config("model_profiles.yaml")["profiles"]
        profile = profiles[self.profile_key][task.language.value]
        return AdapterGuidance(
            role=profile["role"],
            execution_rules=profile.get("execution_rules", []),
            final_report=profile.get("final_report", []),
            required_dimensions=profile.get("required_dimensions", []),
        )
