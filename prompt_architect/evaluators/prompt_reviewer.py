from __future__ import annotations

import re

from prompt_architect.schemas import (
    Language,
    PromptArtifact,
    PromptStrategy,
    ReviewIssue,
    ReviewResult,
    ReviewSeverity,
    TaskSpec,
)
from prompt_architect.security import contains_secret, redact_secrets


_FALSE_CLAIM_PATTERNS = (
    r"(?:必须|务必)声称(?:测试|检查).*(?:通过|完成)",
    r"(?:claim|state) that all (?:tests|checks) passed",
    r"即使.*未运行.*(?:也|仍).*(?:通过|完成)",
)
_UNVERIFIABLE_PATTERNS = (r"保证完美", r"100%无错误", r"绝对正确", r"guarantee perfection", r"100% error[- ]free", r"flawless")
_BROAD_CHANGE_PATTERNS = (r"覆盖整个仓库", r"重写全部代码", r"rewrite the entire repository", r"overwrite all code")


class PromptReviewer:
    _DEDUCTIONS = {
        ReviewSeverity.INFO: 2,
        ReviewSeverity.WARNING: 5,
        ReviewSeverity.MAJOR: 15,
        ReviewSeverity.CRITICAL: 30,
    }

    def review(
        self,
        task: TaskSpec,
        artifacts: list[PromptArtifact],
        strategy: PromptStrategy,
        *,
        repair_attempted: bool = False,
    ) -> ReviewResult:
        issues: list[ReviewIssue] = []
        if not task.normalized_goal:
            issues.append(self._issue(task, "missing_goal", ReviewSeverity.CRITICAL, "缺少明确任务目标。", "The task goal is missing."))
        if not task.deliverables:
            issues.append(self._issue(task, "missing_deliverables", ReviewSeverity.CRITICAL, "缺少最终产物。", "Deliverables are missing."))
        if not task.acceptance_criteria:
            issues.append(self._issue(task, "missing_acceptance", ReviewSeverity.CRITICAL, "缺少验收标准。", "Acceptance criteria are missing."))
        if not artifacts:
            issues.append(self._issue(task, "no_artifacts", ReviewSeverity.CRITICAL, "编译器没有生成任何产物。", "The compiler generated no artifacts."))

        corpus = "\n".join(artifact.content for artifact in artifacts)
        for artifact in artifacts:
            if contains_secret(artifact.content):
                issues.append(
                    self._issue(
                        task,
                        "secret_detected",
                        ReviewSeverity.CRITICAL,
                        "生成物包含疑似密码、Token 或 API Key。",
                        "The artifact may contain a password, token, or API key.",
                        artifact=artifact.filename,
                        repairable=True,
                    )
                )

        self._pattern_issues(task, artifacts, _FALSE_CLAIM_PATTERNS, issues, "fabricated_execution", ReviewSeverity.CRITICAL, "提示词要求伪造执行或测试结果。", "The prompt asks for fabricated execution or test results.")
        self._pattern_issues(task, artifacts, _UNVERIFIABLE_PATTERNS, issues, "unverifiable_requirement", ReviewSeverity.MAJOR, "存在无法客观验证的绝对要求。", "The prompt contains an objectively unverifiable absolute requirement.")
        self._pattern_issues(task, artifacts, _BROAD_CHANGE_PATTERNS, issues, "broad_repository_change", ReviewSeverity.CRITICAL, "提示词存在大范围覆盖仓库的风险。", "The prompt risks broad repository overwrite.")

        if self._has_conflict(task):
            issues.append(
                self._issue(task, "conflicting_requirements", ReviewSeverity.CRITICAL, "任务目标与禁止事项互相冲突。", "The goal conflicts with a forbidden action.")
            )
        required_count = sum(1 for path in task.available_files if path)
        if required_count > 20:
            issues.append(
                self._issue(task, "excessive_context", ReviewSeverity.MAJOR, "一次提供的文件上下文过多，应建立索引并按需读取。", "Too many files are supplied at once; index and load them on demand.")
            )
        if strategy in {PromptStrategy.COMPACT, PromptStrategy.STRUCTURED}:
            stage_tokens = len(re.findall(r"阶段(?:一|二|三|四|五|六|\s*\d+)", corpus, re.IGNORECASE)) + len(
                re.findall(r"\bstage\s+\d+", corpus, re.IGNORECASE)
            )
            if stage_tokens >= 3:
                issues.append(
                    self._issue(task, "mixed_stages", ReviewSeverity.MAJOR, "单条提示词混入过多执行阶段。", "The single prompt mixes too many execution stages.")
                )

        max_length = 8_000 if strategy == PromptStrategy.COMPACT else 15_000
        if len(corpus) > max_length and strategy in {PromptStrategy.COMPACT, PromptStrategy.STRUCTURED}:
            issues.append(
                self._issue(task, "prompt_too_long", ReviewSeverity.WARNING, "提示词可能可以进一步压缩。", "The prompt may be compressible.")
            )

        score = max(0, 100 - sum(self._DEDUCTIONS[issue.severity] for issue in issues))
        passed = not any(issue.severity == ReviewSeverity.CRITICAL for issue in issues) and score >= 70
        suggestions = self._suggestions(task, issues)
        return ReviewResult(
            passed=passed,
            score=score,
            issues=issues,
            suggestions=suggestions,
            repair_attempted=repair_attempted,
        )

    def review_text(self, text: str, *, language: Language = Language.ZH_CN) -> ReviewResult:
        issues: list[ReviewIssue] = []
        checks = (
            (r"(?:任务目标|\bgoal\b|\bobjective\b)", "missing_goal", "缺少目标章节。", "A goal section is missing."),
            (r"(?:输出产物|输出要求|交付物|\bdeliverables?\b|\boutput requirements?\b)", "missing_deliverables", "缺少产物章节。", "A deliverables section is missing."),
            (r"(?:验收标准|acceptance criteria)", "missing_acceptance", "缺少验收标准章节。", "An acceptance criteria section is missing."),
        )
        for pattern, code, zh, en in checks:
            if not re.search(pattern, text, re.IGNORECASE):
                issues.append(ReviewIssue(code=code, severity=ReviewSeverity.MAJOR, message=zh if language == Language.ZH_CN else en))
        if contains_secret(text):
            issues.append(
                ReviewIssue(
                    code="secret_detected",
                    severity=ReviewSeverity.CRITICAL,
                    message="检测到疑似敏感信息。" if language == Language.ZH_CN else "Potential secret detected.",
                    repairable=True,
                )
            )
        for pattern in (*_FALSE_CLAIM_PATTERNS, *_UNVERIFIABLE_PATTERNS, *_BROAD_CHANGE_PATTERNS):
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(
                    ReviewIssue(
                        code="unsafe_requirement",
                        severity=ReviewSeverity.CRITICAL,
                        message="检测到不安全或不可验证要求。" if language == Language.ZH_CN else "Unsafe or unverifiable requirement detected.",
                        repairable=True,
                    )
                )
                break
        score = max(0, 100 - sum(self._DEDUCTIONS[item.severity] for item in issues))
        return ReviewResult(
            passed=not any(item.severity == ReviewSeverity.CRITICAL for item in issues) and score >= 70,
            score=score,
            issues=issues,
            suggestions=[],
        )

    def repair(self, artifacts: list[PromptArtifact]) -> list[PromptArtifact]:
        repaired: list[PromptArtifact] = []
        replacements = {
            "保证完美": "满足已列出的可验证验收标准",
            "100%无错误": "通过已列出的可执行检查",
            "绝对正确": "以验证证据支持结论",
            "guarantee perfection": "meet the listed verifiable acceptance criteria",
            "100% error-free": "pass the listed executable checks",
            "flawless": "meets the stated acceptance criteria",
            "覆盖整个仓库": "仅修改完成任务所需的文件",
            "重写全部代码": "实施最小充分修改",
            "rewrite the entire repository": "change only the files required by the task",
            "overwrite all code": "make the minimum sufficient change",
        }
        for artifact in artifacts:
            content, _ = redact_secrets(artifact.content)
            for source, target in replacements.items():
                content = re.sub(re.escape(source), target, content, flags=re.IGNORECASE)
            content = re.sub(
                r"(?:必须|务必)声称(?:测试|检查).*(?:通过|完成)",
                "必须如实报告实际执行的测试、失败和无法运行项。",
                content,
                flags=re.IGNORECASE,
            )
            content = re.sub(
                r"(?:claim|state) that all (?:tests|checks) passed",
                "truthfully report which tests ran, failed, or were unavailable",
                content,
                flags=re.IGNORECASE,
            )
            lines: list[str] = []
            for line in content.splitlines():
                if lines and line.startswith("- ") and line == lines[-1]:
                    continue
                lines.append(line.rstrip())
            repaired.append(PromptArtifact(filename=artifact.filename, content="\n".join(lines).strip() + "\n"))
        return repaired

    def _pattern_issues(
        self,
        task: TaskSpec,
        artifacts: list[PromptArtifact],
        patterns: tuple[str, ...],
        issues: list[ReviewIssue],
        code: str,
        severity: ReviewSeverity,
        zh: str,
        en: str,
    ) -> None:
        for artifact in artifacts:
            if any(re.search(pattern, artifact.content, re.IGNORECASE) for pattern in patterns):
                issues.append(self._issue(task, code, severity, zh, en, artifact=artifact.filename, repairable=True))

    @staticmethod
    def _has_conflict(task: TaskSpec) -> bool:
        goal = task.normalized_goal.casefold()
        forbidden = " ".join(task.forbidden_actions).casefold()
        delete_goal = any(word in goal for word in ("删除", "delete", "remove"))
        delete_forbidden = any(word in forbidden for word in ("不得删除", "禁止删除", "do not delete", "must not delete"))
        modify_goal = any(word in goal for word in ("修改", "实现", "重构", "modify", "implement", "refactor"))
        modify_forbidden = any(word in forbidden for word in ("不得修改", "禁止修改", "do not modify", "must not modify"))
        return (delete_goal and delete_forbidden) or (modify_goal and modify_forbidden)

    def _issue(
        self,
        task: TaskSpec,
        code: str,
        severity: ReviewSeverity,
        zh: str,
        en: str,
        *,
        artifact: str | None = None,
        repairable: bool = False,
    ) -> ReviewIssue:
        return ReviewIssue(
            code=code,
            severity=severity,
            message=zh if task.language == Language.ZH_CN else en,
            artifact=artifact,
            repairable=repairable,
        )

    @staticmethod
    def _suggestions(task: TaskSpec, issues: list[ReviewIssue]) -> list[str]:
        if not issues:
            return []
        if task.language == Language.ZH_CN:
            return ["修复严重问题并重新执行质量检查。"]
        return ["Fix severe issues and run the quality review again."]
