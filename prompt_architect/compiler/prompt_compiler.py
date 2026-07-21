from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from prompt_architect.context import ContextManager
from prompt_architect.schemas import (
    AdapterGuidance,
    ContextManifest,
    Language,
    PromptArtifact,
    PromptStrategy,
    TaskSpec,
    TaskType,
)


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    goal: str
    inputs: list[str]
    allowed_actions: list[str]
    outputs: list[str]
    next_dependency: str


class PromptCompiler:
    def __init__(self, context_manager: ContextManager | None = None) -> None:
        self.context_manager = context_manager or ContextManager()
        self.environment = Environment(
            loader=PackageLoader("prompt_architect", "templates"),
            undefined=StrictUndefined,
            autoescape=select_autoescape(default_for_string=False, default=False),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def compile(
        self,
        task: TaskSpec,
        manifest: ContextManifest,
        guidance: AdapterGuidance,
        strategy: PromptStrategy,
    ) -> list[PromptArtifact]:
        if strategy == PromptStrategy.COMPACT:
            artifacts = [PromptArtifact(filename="PROMPT.md", content=self._render("compact/prompt", task, manifest, guidance))]
        elif strategy == PromptStrategy.STRUCTURED:
            artifacts = [PromptArtifact(filename="PROMPT.md", content=self._render("structured/prompt", task, manifest, guidance))]
        elif strategy == PromptStrategy.STAGED:
            artifacts = self._compile_staged(task, manifest, guidance)
        else:
            artifacts = self._compile_project(task, manifest, guidance)

        if not any(artifact.filename == "CONTEXT_MANIFEST.md" for artifact in artifacts):
            artifacts.append(
                PromptArtifact(
                    filename="CONTEXT_MANIFEST.md",
                    content=self.context_manager.render_markdown(task, manifest),
                )
            )
        return artifacts

    def _template_name(self, base: str, language: Language) -> str:
        suffix = "zh" if language == Language.ZH_CN else "en"
        return f"{base}.{suffix}.md.j2"

    def _render(
        self,
        base: str,
        task: TaskSpec,
        manifest: ContextManifest,
        guidance: AdapterGuidance,
        **extra: object,
    ) -> str:
        template = self.environment.get_template(self._template_name(base, task.language))
        context_groups = {category.value: manifest.by_category(category) for category in manifest_category_values()}
        return template.render(
            task=task,
            guidance=guidance,
            manifest=manifest,
            context_groups=context_groups,
            **extra,
        ).strip() + "\n"

    def _compile_staged(
        self, task: TaskSpec, manifest: ContextManifest, guidance: AdapterGuidance
    ) -> list[PromptArtifact]:
        stages = self._stages(task)
        artifacts = [
            PromptArtifact(
                filename="STAGE_INDEX.md",
                content=self._render("staged/index", task, manifest, guidance, stages=stages),
            )
        ]
        for number, stage in enumerate(stages, start=1):
            artifacts.append(
                PromptArtifact(
                    filename=f"STAGE_{number:02d}_{stage.key.upper()}.md",
                    content=self._render(
                        "staged/stage",
                        task,
                        manifest,
                        guidance,
                        stage=stage,
                        stage_number=number,
                        stage_count=len(stages),
                    ),
                )
            )
        return artifacts

    def _compile_project(
        self, task: TaskSpec, manifest: ContextManifest, guidance: AdapterGuidance
    ) -> list[PromptArtifact]:
        phase_specs = self._project_phases(task)
        artifacts = [
            PromptArtifact(
                filename="PROJECT_BRIEF.md",
                content=self._render("project/brief", task, manifest, guidance),
            )
        ]
        for filename, phase in phase_specs:
            artifacts.append(
                PromptArtifact(
                    filename=filename,
                    content=self._render("project/phase", task, manifest, guidance, stage=phase),
                )
            )
        artifacts.extend(
            [
                PromptArtifact(
                    filename="CONTEXT_MANIFEST.md",
                    content=self.context_manager.render_markdown(task, manifest),
                ),
                PromptArtifact(
                    filename="ACCEPTANCE_CRITERIA.md",
                    content=self._render("project/acceptance", task, manifest, guidance),
                ),
            ]
        )
        return artifacts

    def _stages(self, task: TaskSpec) -> list[Stage]:
        zh = task.language == Language.ZH_CN
        names = (
            [
                ("analyze", "分析现状", "确认现有结构、事实、约束和风险。", ["任务说明", "上下文清单"], ["只读检查相关资料", "记录缺失信息和假设"], ["现状分析", "范围与风险清单"], "经确认的现状分析"),
                ("design", "设计方案", "定义架构、边界、接口和验证方法。", ["阶段一输出"], ["比较必要方案", "形成最小充分设计"], ["设计说明", "接口约定", "实施清单"], "已确认的设计与接口"),
                ("implement", "实现核心功能", "按设计完成范围内实现。", ["阶段二输出", "相关源文件"], ["保留既有改动", "实施最小充分修改"], task.deliverables[:2] or ["实现结果"], "可运行的实现与变更清单"),
                ("test", "测试与修复", "运行可执行验证并修复范围内问题。", ["阶段三实现", "验收标准"], ["实际运行检查", "如实记录失败和限制"], ["测试结果", "必要修复"], "已验证的实现"),
                ("document", "整理交付", "整理文档和最终核查报告。", ["前序全部输出"], ["核对验收标准", "记录遗留问题"], task.deliverables, "任务完成"),
            ]
            if zh
            else [
                ("analyze", "Analyze current state", "Confirm existing structure, facts, constraints, and risks.", ["Task brief", "Context manifest"], ["Inspect relevant material read-only", "Record missing facts and assumptions"], ["Current-state analysis", "Scope and risk list"], "Confirmed current-state analysis"),
                ("design", "Design the solution", "Define architecture, boundaries, interfaces, and validation.", ["Stage 1 output"], ["Compare only necessary options", "Create a minimum sufficient design"], ["Design", "Interface contract", "Implementation checklist"], "Approved design and interfaces"),
                ("implement", "Implement core behavior", "Implement the approved scope.", ["Stage 2 output", "Relevant source files"], ["Preserve existing changes", "Make the minimum sufficient change"], task.deliverables[:2] or ["Implementation"], "Runnable implementation and change list"),
                ("test", "Test and repair", "Run available validation and fix in-scope defects.", ["Stage 3 implementation", "Acceptance criteria"], ["Actually run checks", "Report failures and limits truthfully"], ["Test results", "Necessary fixes"], "Validated implementation"),
                ("document", "Prepare delivery", "Finalize documentation and verification report.", ["All previous outputs"], ["Check every acceptance criterion", "Record open issues"], task.deliverables, "Task complete"),
            ]
        )
        return [Stage(*values) for values in names]

    def _project_phases(self, task: TaskSpec) -> list[tuple[str, Stage]]:
        zh = task.language == Language.ZH_CN
        if zh:
            phases = [
                ("ARCHITECTURE_PROMPT.md", Stage("architecture", "项目分析与架构设计", "分析上下文并定义系统边界、模块、接口和风险。", ["PROJECT_BRIEF.md", "CONTEXT_MANIFEST.md"], ["先只读分析", "不得开始大规模实现"], ["架构说明", "接口清单", "风险与决策记录"], "架构评审通过")),
                ("IMPLEMENTATION_PROMPT.md", Stage("implementation", "分批实现", "依据已确认架构分批实现并持续验证。", ["架构阶段产物", "相关源文件"], ["维护实施清单", "最小范围修改", "每批运行相关检查"], task.deliverables, "可测试的完整实现")),
                ("TEST_PROMPT.md", Stage("test", "系统测试与修复", "按验收标准执行单元、集成及可用的端到端验证。", ["完整实现", "ACCEPTANCE_CRITERIA.md"], ["实际运行检查", "只修复可复现且范围内的问题"], ["测试证据", "缺陷与修复记录"], "测试结果可供独立复核")),
                ("REVIEW_PROMPT.md", Stage("review", "最终审查", "独立核查范围、质量、风险、文档和验收状态。", ["全部项目产物", "测试证据"], ["不伪造验证", "区分已完成与未验证"], ["审查结论", "遗留问题", "发布建议"], "项目交付完成")),
            ]
        else:
            phases = [
                ("ARCHITECTURE_PROMPT.md", Stage("architecture", "Analyze and design architecture", "Analyze context and define boundaries, modules, interfaces, and risks.", ["PROJECT_BRIEF.md", "CONTEXT_MANIFEST.md"], ["Start with read-only analysis", "Do not begin broad implementation"], ["Architecture", "Interface list", "Risk and decision log"], "Architecture approved")),
                ("IMPLEMENTATION_PROMPT.md", Stage("implementation", "Implement incrementally", "Implement the approved architecture in verifiable batches.", ["Architecture outputs", "Relevant source files"], ["Maintain an implementation checklist", "Make minimum changes", "Run checks for each batch"], task.deliverables, "Complete testable implementation")),
                ("TEST_PROMPT.md", Stage("test", "Test and repair the system", "Run unit, integration, and available end-to-end checks against acceptance criteria.", ["Complete implementation", "ACCEPTANCE_CRITERIA.md"], ["Actually run checks", "Fix only reproduced in-scope defects"], ["Test evidence", "Defect and repair log"], "Independently reviewable test result")),
                ("REVIEW_PROMPT.md", Stage("review", "Final review", "Independently verify scope, quality, risk, documentation, and acceptance status.", ["All project artifacts", "Test evidence"], ["Never fabricate verification", "Separate completed from unverified work"], ["Review conclusion", "Open issues", "Release recommendation"], "Project delivery complete")),
            ]
        return phases


def manifest_category_values():
    from prompt_architect.schemas import ContextCategory

    return list(ContextCategory)
