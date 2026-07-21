from prompt_architect.schemas import ComplexityAssessment, Language, PromptStrategy, RoutingDecision, TaskSpec


class StrategyRouter:
    def route(self, task: TaskSpec, assessment: ComplexityAssessment) -> RoutingDecision:
        recommended = assessment.recommended_strategy
        if task.allow_staged or recommended in {PromptStrategy.COMPACT, PromptStrategy.STRUCTURED}:
            return RoutingDecision(
                recommended_strategy=recommended,
                selected_strategy=recommended,
                reason=assessment.reason,
            )

        if recommended == PromptStrategy.STAGED:
            warning = (
                "用户禁止分阶段执行；已降级为结构化提示词，执行风险和上下文压力会增加。"
                if task.language == Language.ZH_CN
                else "Staging is disabled; the task was downgraded to one structured prompt with higher execution risk."
            )
            return RoutingDecision(
                recommended_strategy=recommended,
                selected_strategy=PromptStrategy.STRUCTURED,
                reason=warning,
                warnings=[warning],
            )

        reason = (
            "项目级任务无法安全压缩为单条提示词；请允许分阶段执行。"
            if task.language == Language.ZH_CN
            else "A project-level task cannot be safely compressed into one prompt; enable staged execution."
        )
        return RoutingDecision(
            recommended_strategy=recommended,
            selected_strategy=None,
            blocked=True,
            reason=reason,
            warnings=[reason],
        )
