from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from uuid import uuid4

from prompt_architect.llm.context import ContextBundle, ContextGrantStore, ContextLoader
from prompt_architect.llm.deepseek import DeepSeekProvider, ProviderError
from prompt_architect.llm.models import ModelUsage
from prompt_architect.llm.orchestrator import AgentOrchestrator, AgentQualityError
from prompt_architect.schemas import TargetAgent
from prompt_architect.security import redact_secrets
from prompt_architect.service import MissingInformationError, QualityGateError, StrategyBlockedError
from prompt_architect.web.models import (
    AgentSessionCreate,
    AgentSessionDetail,
    AgentSessionSummary,
    GenerationRequest,
)
from prompt_architect.web.runs import RunService


@dataclass
class SessionRuntime:
    request: AgentSessionCreate
    answers: list[str] = field(default_factory=list)
    active_task: asyncio.Task | None = None


class AgentService:
    def __init__(
        self,
        runs: RunService,
        provider: DeepSeekProvider,
        grants: ContextGrantStore,
    ) -> None:
        self.runs = runs
        self.provider = provider
        self.grants = grants
        self.loader = ContextLoader()
        self.orchestrator = AgentOrchestrator(provider)
        self._runtime: dict[str, SessionRuntime] = {}
        self.runs.history.fail_incomplete_agent_sessions()

    def create(self, request: AgentSessionCreate) -> AgentSessionDetail:
        identifier = str(uuid4())
        sanitized, _ = redact_secrets(request.raw_request)
        target = request.target_agent.value if request.target_agent else TargetAgent.CHAT_MODEL.value
        self.runs.history.create_agent_session(
            session_id=identifier,
            sanitized_request=sanitized,
            target_agent=target,
            language=request.language.value,
            provider="offline_rules" if request.offline_rules else "deepseek",
            model_id=request.model_id,
        )
        self.runs.history.add_agent_message(identifier, "user", sanitized)
        self._runtime[identifier] = SessionRuntime(request=request)
        detail = self.get(identifier)
        if detail is None:
            raise RuntimeError("无法创建智能体会话。")
        return detail

    def get(self, session_id: str) -> AgentSessionDetail | None:
        data = self.runs.history.get_agent_session(session_id)
        if data is None:
            return None
        run = self.runs.get(data["run_id"]) if data.get("run_id") else None
        return AgentSessionDetail(
            id=data["id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            status=data["status"],
            sanitized_request=data["sanitized_request"],
            target_agent=data["target_agent"],
            language=data["language"],
            provider=data["provider"],
            model_id=data["model_id"],
            clarification_round=data["clarification_round"],
            questions=data["questions"],
            run_id=data["run_id"],
            last_error=data["last_error"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            total_tokens=data["total_tokens"],
            run=run,
        )

    def list(self) -> list[AgentSessionSummary]:
        return [AgentSessionSummary.model_validate(item) for item in self.runs.history.list_agent_sessions()]

    async def stream_turn(self, session_id: str, answers: list[str]) -> AsyncIterator[dict[str, Any]]:
        runtime = self._runtime.get(session_id)
        if runtime is None:
            raise KeyError(session_id)
        current = self.get(session_id)
        if current is None or current.status in {"completed", "failed", "cancelled"}:
            raise ValueError("该会话已经结束。")
        if current.status == "clarifying":
            if len(answers) != len(current.questions) or any(not item.strip() for item in answers):
                raise ValueError("请回答全部补充问题。")
            safe_answers = [redact_secrets(item.strip())[0] for item in answers]
            runtime.answers.extend(safe_answers)
            for answer in safe_answers:
                self.runs.history.add_agent_message(session_id, "user", answer)

        runtime.active_task = asyncio.current_task()
        context_identifiers = runtime.request.context_grants
        try:
            if runtime.request.offline_rules:
                async for event in self._offline(session_id, runtime.request):
                    yield event
                return
            granted_files = self.grants.consume(context_identifiers) if context_identifiers else []
            context = self.loader.load(granted_files) if granted_files else ContextBundle("", [], [])
            model = await self._model(runtime.request.model_id)
            self.runs.history.update_agent_session(session_id, model_id=model, status="pending", last_error=None)
            yield self._event("stage.started", stage="understanding", message="正在理解你的需求…")
            analysis = await self.orchestrator.analyze(
                runtime.request.model_dump(mode="json"),
                model=model,
                context=context,
                answers=runtime.answers,
            )
            self._record_usage(session_id, analysis.usage)
            yield self._event(
                "analysis.completed",
                analysis={
                    "task": analysis.task.model_dump(mode="json"),
                    "complexity": analysis.assessment.model_dump(mode="json"),
                    "routing": analysis.routing.model_dump(mode="json"),
                    "blockers": analysis.task.blocking_questions,
                },
            )
            if analysis.task.blocking_questions:
                next_round = current.clarification_round + 1
                if next_round > 3:
                    raise ValueError("补充三轮后仍缺少关键信息，请重新描述任务。")
                questions = analysis.task.blocking_questions[:3]
                self.runs.history.update_agent_session(
                    session_id,
                    status="clarifying",
                    clarification_round=next_round,
                    questions_json=json.dumps(questions, ensure_ascii=False),
                )
                for question in questions:
                    self.runs.history.add_agent_message(session_id, "assistant", question)
                yield self._event("questions.required", questions=questions, round=next_round)
                return
            if analysis.routing.blocked:
                raise ValueError(analysis.routing.reason)

            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def on_stage(stage: str) -> None:
                status, message = {
                    "generating": ("generating", "正在生成提示词…"),
                    "reviewing": ("reviewing", "正在独立检查质量…"),
                    "repairing": ("repairing", "发现问题，正在修复一次…"),
                }[stage]
                self.runs.history.update_agent_session(session_id, status=status)
                await queue.put(self._event("stage.started", stage=stage, message=message))

            generation_task = asyncio.create_task(
                self.orchestrator.generate(analysis, model=model, context=context, on_stage=on_stage)
            )
            while not generation_task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield event
                except TimeoutError:
                    continue
            while not queue.empty():
                yield queue.get_nowait()
            generated = await generation_task
            self._record_usage(session_id, generated.usage)
            run = self.runs.publish_result(generated.result)
            self.runs.history.update_agent_session(
                session_id,
                status="completed",
                run_id=run.id,
                questions_json="[]",
            )
            completed = self.get(session_id)
            yield self._event(
                "run.published",
                run=run.model_dump(mode="json"),
                repaired=generated.repaired,
                critic_score=generated.critic.score,
                model=model,
                usage={
                    "input_tokens": completed.input_tokens if completed else 0,
                    "output_tokens": completed.output_tokens if completed else 0,
                    "total_tokens": completed.total_tokens if completed else 0,
                },
            )
        except asyncio.CancelledError:
            self.runs.history.update_agent_session(session_id, status="cancelled", last_error="生成已取消。")
            yield self._event("cancelled", message="生成已取消。")
        except (ProviderError, AgentQualityError, ValueError, MissingInformationError, StrategyBlockedError, QualityGateError) as exc:
            message = str(exc)
            self.runs.history.update_agent_session(session_id, status="failed", last_error=message)
            yield self._event("failed", code=getattr(exc, "code", "agent_failed"), message=message)
        finally:
            runtime.active_task = None
            detail = self.get(session_id)
            if detail and detail.status in {"completed", "failed", "cancelled"}:
                self.grants.release(context_identifiers)
                self._runtime.pop(session_id, None)

    def cancel(self, session_id: str) -> bool:
        runtime = self._runtime.get(session_id)
        if runtime is None:
            return False
        if runtime.active_task and not runtime.active_task.done():
            runtime.active_task.cancel()
        else:
            self.runs.history.update_agent_session(session_id, status="cancelled", last_error="生成已取消。")
            self.grants.release(runtime.request.context_grants)
            self._runtime.pop(session_id, None)
        return True

    async def _offline(self, session_id: str, request: AgentSessionCreate) -> AsyncIterator[dict[str, Any]]:
        self.runs.history.update_agent_session(session_id, status="generating", model_id="offline-rules")
        yield self._event("stage.started", stage="offline", message="正在使用规则离线生成…")
        payload = GenerationRequest.model_validate(
            request.model_dump(exclude={"model_id", "offline_rules", "context_grants"})
        )
        run = self.runs.create(payload)
        self.runs.history.update_agent_session(session_id, status="completed", run_id=run.id)
        yield self._event("run.published", run=run.model_dump(mode="json"), repaired=False, critic_score=None)

    async def _model(self, requested: str) -> str:
        models = await self.provider.list_models()
        ids = [item.id for item in models]
        configured = self.runs.history.get_setting("deepseek.default_model", "auto")
        selected = requested if requested != "auto" else configured
        if selected != "auto":
            if selected not in ids:
                raise ProviderError("model_unavailable", "所选 DeepSeek 模型当前不可用，请重新选择。")
            return selected
        preferred = next((item for item in ids if "chat" in item.casefold()), None)
        if preferred:
            return preferred
        non_reasoner = next((item for item in ids if "reason" not in item.casefold()), None)
        return non_reasoner or ids[0]

    def _record_usage(self, session_id: str, usage: ModelUsage) -> None:
        self.runs.history.add_model_usage(
            session_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

    @staticmethod
    def _event(event: str, **data: Any) -> dict[str, Any]:
        return {"event": event, "data": data}
