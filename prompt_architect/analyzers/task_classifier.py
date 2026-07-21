from __future__ import annotations

from dataclasses import dataclass

from prompt_architect.config_loader import load_config
from prompt_architect.schemas import TargetAgent, TaskType


@dataclass(frozen=True)
class ClassificationResult:
    task_type: TaskType
    subtypes: list[str]
    matched_keywords: list[str]


class RuleTaskClassifier:
    """Priority-ordered keyword classifier with an LLM-replaceable interface."""

    def __init__(self) -> None:
        self.config = load_config("task_types.yaml")

    def classify(self, request: str) -> ClassificationResult:
        normalized = request.casefold()
        candidates: list[tuple[int, int, str, dict[str, object], list[str]]] = []
        for type_name, rule in self.config["task_types"].items():
            matches = [keyword for keyword in rule.get("keywords", []) if keyword.casefold() in normalized]
            if matches:
                candidates.append((int(rule.get("priority", 0)), len(matches), type_name, rule, matches))

        if not candidates:
            return ClassificationResult(TaskType.GENERAL, [], [])

        _, _, type_name, rule, matches = max(candidates, key=lambda item: (item[0], item[1]))
        subtypes = [
            subtype
            for subtype, keywords in rule.get("subtypes", {}).items()
            if any(keyword.casefold() in normalized for keyword in keywords)
        ]
        return ClassificationResult(TaskType(type_name), subtypes, matches)

    def infer_target(self, task_type: TaskType) -> TargetAgent:
        value = self.config["target_inference"].get(task_type.value, "chat_model")
        return TargetAgent(value)
