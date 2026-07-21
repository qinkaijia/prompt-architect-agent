from __future__ import annotations

import re
from collections.abc import Iterable

from prompt_architect.analyzers.task_classifier import RuleTaskClassifier
from prompt_architect.schemas import Language, RiskLevel, TargetAgent, TaskSpec, TaskType
from prompt_architect.security import redact_secrets


_PATH_PATTERN = re.compile(
    r"(?<![\w])(?:[A-Za-z]:[\\/])?[\w.@+()\-]+(?:[\\/][\w.@+()\-]+)*\.(?:py|ya?ml|json|toml|md|txt|pdf|csv|xlsx?|docx?|pptx?|c|h|cpp|hpp|js|ts|tsx|vue)(?![\w])",
    re.IGNORECASE,
)
_EXPLICIT_TARGETS: tuple[tuple[TargetAgent, tuple[str, ...]], ...] = (
    (TargetAgent.CLAUDE_CODE, ("claude code", "claude-code")),
    (TargetAgent.CODEX, ("codex",)),
    (TargetAgent.IMAGE_MODEL, ("图像模型", "image model", "midjourney", "stable diffusion", "dall-e")),
    (TargetAgent.CHAT_MODEL, ("chatgpt", "聊天模型", "通用大模型", "chat model")),
)
_VAGUE_REQUESTS = (
    "帮我优化一下这个项目",
    "优化一下",
    "改进一下",
    "处理一下",
    "帮我做一下",
    "make it better",
    "improve this project",
    "optimize this",
)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


class RequirementAnalyzer:
    def __init__(self, classifier: RuleTaskClassifier | None = None) -> None:
        self.classifier = classifier or RuleTaskClassifier()

    def analyze(
        self,
        raw_request: str,
        *,
        target_agent: TargetAgent | None = None,
        deliverables: list[str] | None = None,
        known_context: list[str] | None = None,
        available_files: list[str] | None = None,
        constraints: list[str] | None = None,
        forbidden_actions: list[str] | None = None,
        tools: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        language: Language = Language.ZH_CN,
        allow_staged: bool = True,
    ) -> TaskSpec:
        sanitized, secret_found = redact_secrets(raw_request.strip())
        classification = self.classifier.classify(sanitized)
        inferred: list[str] = []
        sources: dict[str, str] = {"raw_request": "user", "language": "user_or_default"}

        explicit_target = target_agent or self._target_from_text(sanitized)
        selected_target = explicit_target or self.classifier.infer_target(classification.task_type)
        sources["target_agent"] = "user" if explicit_target else "rule_inference"
        if not explicit_target:
            inferred.append("target_agent")

        normalized_goal = self._normalize_goal(sanitized)
        resolved_deliverables = _unique(deliverables or self._default_deliverables(classification.task_type, language))
        resolved_acceptance = _unique(
            acceptance_criteria or self._default_acceptance(classification.task_type, selected_target, language)
        )
        resolved_context = _unique(known_context or [])
        resolved_constraints = _unique(constraints or [])
        resolved_forbidden = _unique(forbidden_actions or [])
        resolved_tools = _unique(tools or self._tools_from_text(sanitized))

        if deliverables is None:
            inferred.append("deliverables")
            sources["deliverables"] = "rule_inference"
        else:
            sources["deliverables"] = "user"
        if acceptance_criteria is None:
            inferred.append("acceptance_criteria")
            sources["acceptance_criteria"] = "rule_inference"
        else:
            sources["acceptance_criteria"] = "user"

        if classification.task_type == TaskType.IMAGE_DESIGN:
            image_defaults = self._image_defaults(sanitized, language)
            for value in image_defaults:
                if value not in resolved_constraints:
                    resolved_constraints.append(value)
            inferred.append("image_defaults")

        missing: list[str] = []
        questions: list[str] = []
        if not normalized_goal:
            missing.append(self._text(language, "任务目标", "task goal"))
            questions.append(self._text(language, "你希望 AI 最终完成什么具体结果？", "What concrete result should the AI produce?"))
        elif self._is_vague(sanitized, classification.task_type):
            missing.extend(
                [
                    self._text(language, "具体优化目标", "specific improvement goal"),
                    self._text(language, "期望产物", "expected deliverable"),
                    self._text(language, "验收方式", "acceptance method"),
                ]
            )
            questions.extend(
                [
                    self._text(language, "需要优化项目的哪个部分，当前问题是什么？", "Which part should improve, and what is wrong now?"),
                    self._text(language, "希望得到哪些可核查的产物？", "Which verifiable deliverables do you expect?"),
                ]
            )

        if secret_found:
            resolved_forbidden.append(
                self._text(language, "不得在生成物中复述或保存用户提供的敏感信息。", "Do not repeat or persist supplied secrets.")
            )

        return TaskSpec(
            raw_request=raw_request,
            sanitized_request=sanitized,
            normalized_goal=normalized_goal,
            task_type=classification.task_type,
            task_subtypes=classification.subtypes,
            target_agent=selected_target,
            deliverables=resolved_deliverables,
            known_context=resolved_context,
            available_files=_unique([*(available_files or []), *_PATH_PATTERN.findall(sanitized)]),
            constraints=resolved_constraints,
            forbidden_actions=resolved_forbidden,
            tools=resolved_tools,
            missing_information=_unique(missing),
            acceptance_criteria=resolved_acceptance,
            risk_level=self._risk_level(sanitized, classification.task_type),
            language=language,
            allow_staged=allow_staged,
            inferred_fields=_unique(inferred),
            field_sources=sources,
            blocking_questions=_unique(questions),
        )

    @staticmethod
    def _text(language: Language, zh: str, en: str) -> str:
        return zh if language == Language.ZH_CN else en

    @staticmethod
    def _normalize_goal(request: str) -> str:
        value = request.strip()
        value = re.sub(r"^(?:请|麻烦|帮我|请帮我)\s*", "", value)
        value = re.sub(r"^(?:please\s+|could you\s+)", "", value, flags=re.IGNORECASE)
        return value.strip("。.!！ \t\r\n")

    @staticmethod
    def _target_from_text(request: str) -> TargetAgent | None:
        normalized = request.casefold()
        for target, keywords in _EXPLICIT_TARGETS:
            if any(keyword in normalized for keyword in keywords):
                return target
        return None

    @staticmethod
    def _is_vague(request: str, task_type: TaskType) -> bool:
        normalized = request.casefold().strip("。.!！ ")
        if normalized in _VAGUE_REQUESTS:
            return True
        generic_objects = ("这个项目", "this project", "it")
        generic_actions = ("优化", "改进", "处理", "improve", "optimize", "fix")
        return task_type == TaskType.GENERAL and len(normalized) < 100 and any(x in normalized for x in generic_objects) and any(
            x in normalized for x in generic_actions
        )

    @staticmethod
    def _tools_from_text(request: str) -> list[str]:
        names = ("pytest", "git", "github", "docker", "hfss", "matlab", "figma", "playwright")
        normalized = request.casefold()
        return [name for name in names if name in normalized]

    def _default_deliverables(self, task_type: TaskType, language: Language) -> list[str]:
        zh: dict[TaskType, list[str]] = {
            TaskType.SOFTWARE_DEVELOPMENT: ["满足目标的代码", "相关测试", "修改说明"],
            TaskType.CODE_DEBUGGING: ["根因说明", "最小修复", "回归测试结果"],
            TaskType.REPOSITORY_REFACTORING: ["重构后的代码", "回归测试", "迁移说明"],
            TaskType.EMBEDDED_SYSTEM: ["系统设计与接口定义", "实现代码", "集成测试方案", "使用文档"],
            TaskType.HARDWARE_DESIGN: ["设计方案", "接口与参数说明", "验证方案"],
            TaskType.SIMULATION: ["仿真配置", "结果与分析", "可复现步骤"],
            TaskType.RESEARCH: ["研究分析结果", "证据与引用", "结论和限制"],
            TaskType.DOCUMENT_WRITING: ["可直接使用的文档"],
            TaskType.DATA_ANALYSIS: ["分析结果", "可复现方法", "关键结论"],
            TaskType.IMAGE_DESIGN: ["符合视觉规格的目标图像"],
            TaskType.PRESENTATION: ["可编辑演示文稿", "内容结构说明"],
            TaskType.AUTOMATION: ["自动化实现", "运行配置", "验证结果"],
            TaskType.AGENT_DEVELOPMENT: ["可运行智能体实现", "配置与模板", "测试和使用文档"],
            TaskType.LEARNING: ["分层讲解", "示例与练习"],
            TaskType.GENERAL: ["与任务目标直接对应的最终结果"],
        }
        en = {
            key: [
                {
                    "满足目标的代码": "Working code that satisfies the goal",
                    "相关测试": "Relevant tests",
                    "修改说明": "Change summary",
                    "根因说明": "Root-cause explanation",
                    "最小修复": "Minimal fix",
                    "回归测试结果": "Regression test results",
                    "重构后的代码": "Refactored code",
                    "回归测试": "Regression tests",
                    "迁移说明": "Migration notes",
                    "系统设计与接口定义": "System design and interface definitions",
                    "实现代码": "Implementation code",
                    "集成测试方案": "Integration test plan",
                    "使用文档": "Usage documentation",
                    "设计方案": "Design proposal",
                    "接口与参数说明": "Interface and parameter specification",
                    "验证方案": "Validation plan",
                    "仿真配置": "Simulation configuration",
                    "结果与分析": "Results and analysis",
                    "可复现步骤": "Reproducible steps",
                    "研究分析结果": "Research analysis",
                    "证据与引用": "Evidence and citations",
                    "结论和限制": "Conclusions and limitations",
                    "可直接使用的文档": "Directly usable document",
                    "分析结果": "Analysis results",
                    "可复现方法": "Reproducible method",
                    "关键结论": "Key conclusions",
                    "符合视觉规格的目标图像": "Target image matching the visual specification",
                    "可编辑演示文稿": "Editable presentation",
                    "内容结构说明": "Content outline",
                    "自动化实现": "Automation implementation",
                    "运行配置": "Runtime configuration",
                    "验证结果": "Validation results",
                    "可运行智能体实现": "Runnable agent implementation",
                    "配置与模板": "Configuration and templates",
                    "测试和使用文档": "Tests and usage documentation",
                    "分层讲解": "Layered explanation",
                    "示例与练习": "Examples and exercises",
                    "与任务目标直接对应的最终结果": "A final result directly matching the goal",
                }[item]
                for item in items
            ]
            for key, items in zh.items()
        }
        return zh[task_type] if language == Language.ZH_CN else en[task_type]

    def _default_acceptance(
        self, task_type: TaskType, target: TargetAgent, language: Language
    ) -> list[str]:
        if target == TargetAgent.IMAGE_MODEL:
            return [
                self._text(language, "画面包含任务要求的模块、布局和文字。", "The image contains the requested modules, layout, and text."),
                self._text(language, "构图、比例、风格和禁止元素均有明确约束。", "Composition, aspect ratio, style, and forbidden elements are explicit."),
            ]
        if task_type in {
            TaskType.SOFTWARE_DEVELOPMENT,
            TaskType.CODE_DEBUGGING,
            TaskType.REPOSITORY_REFACTORING,
            TaskType.EMBEDDED_SYSTEM,
            TaskType.AUTOMATION,
            TaskType.AGENT_DEVELOPMENT,
        }:
            return [
                self._text(language, "交付物覆盖明确的任务目标。", "Deliverables cover the stated goal."),
                self._text(language, "可执行检查被实际运行并如实报告结果。", "Available checks are actually run and reported truthfully."),
                self._text(language, "无关文件和既有用户修改不受影响。", "Unrelated files and existing user changes remain intact."),
            ]
        return [
            self._text(language, "输出完整回应任务目标和约定产物。", "The output fully addresses the goal and agreed deliverables."),
            self._text(language, "假设、限制和无法验证内容均被明确标记。", "Assumptions, limitations, and unverified claims are clearly labeled."),
        ]

    def _image_defaults(self, request: str, language: Language) -> list[str]:
        chinese_text = "中文" in request or language == Language.ZH_CN
        return [
            self._text(language, "未指定时采用横向 16:9 比例。", "Use a landscape 16:9 canvas unless specified otherwise."),
            self._text(language, "采用清晰、克制、层级明确的专业布局。", "Use a clear, restrained professional layout with strong hierarchy."),
            self._text(language, "禁止水印、品牌标识和无关装饰。", "No watermarks, brand marks, or unrelated decoration."),
            ("画面文字使用中文。" if chinese_text else "Use English labels."),
        ]

    @staticmethod
    def _risk_level(request: str, task_type: TaskType) -> RiskLevel:
        text = request.casefold()
        if any(word in text for word in ("删除数据", "生产数据库", "高压", "医疗", "delete data", "production database")):
            return RiskLevel.CRITICAL
        if task_type in {TaskType.EMBEDDED_SYSTEM, TaskType.HARDWARE_DESIGN} or any(
            word in text for word in ("部署", "凭据", "密码", "api key", "security", "hardware", "deploy")
        ):
            return RiskLevel.HIGH
        if task_type in {
            TaskType.SOFTWARE_DEVELOPMENT,
            TaskType.CODE_DEBUGGING,
            TaskType.REPOSITORY_REFACTORING,
            TaskType.AUTOMATION,
            TaskType.AGENT_DEVELOPMENT,
        }:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
