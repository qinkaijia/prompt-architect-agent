from __future__ import annotations

import json
from pathlib import Path
from threading import Timer
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from prompt_architect.evaluators import PromptReviewer
from prompt_architect.schemas import Language, ReviewResult, TargetAgent
from prompt_architect.service import (
    MissingInformationError,
    PromptArchitect,
    QualityGateError,
    StrategyBlockedError,
)


app = typer.Typer(
    name="prompt-architect",
    help="Analyze a task and compile the smallest sufficient prompt strategy.",
    no_args_is_help=True,
)
console = Console()


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.replace("；", ";").replace("，", ",").replace(";", ",").split(",") if item.strip()]


def _target(value: str) -> TargetAgent | None:
    if not value.strip():
        return None
    try:
        return TargetAgent(value.strip().casefold())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in TargetAgent)
        raise typer.BadParameter(f"target agent must be one of: {allowed}") from exc


def _show_analysis(task, assessment, decision) -> None:
    table = Table(title="任务分析" if task.language == Language.ZH_CN else "Task Analysis")
    table.add_column("项目" if task.language == Language.ZH_CN else "Item")
    table.add_column("结果" if task.language == Language.ZH_CN else "Result")
    table.add_row("任务类型" if task.language == Language.ZH_CN else "Task type", task.task_type.value)
    table.add_row("目标 AI" if task.language == Language.ZH_CN else "Target AI", task.target_agent.value)
    table.add_row("复杂度" if task.language == Language.ZH_CN else "Complexity", f"{assessment.total_score}/18")
    table.add_row("推荐策略" if task.language == Language.ZH_CN else "Recommended", decision.recommended_strategy.value)
    table.add_row("采用策略" if task.language == Language.ZH_CN else "Selected", decision.selected_strategy.value if decision.selected_strategy else "BLOCKED")
    console.print(table)
    console.print(decision.reason)
    if task.missing_information:
        console.print("[yellow]缺失信息：[/yellow]" if task.language == Language.ZH_CN else "[yellow]Missing information:[/yellow]")
        for item in task.missing_information:
            console.print(f"- {item}")


def _show_review(review: ReviewResult) -> None:
    color = "green" if review.passed else "red"
    console.print(f"[{color}]Quality score: {review.score}/100 — {'PASS' if review.passed else 'FAIL'}[/{color}]")
    for issue in review.issues:
        location = f" ({issue.artifact})" if issue.artifact else ""
        console.print(f"- [{issue.severity.value}] {issue.code}{location}: {issue.message}")
    for suggestion in review.suggestions:
        console.print(f"- suggestion: {suggestion}")


@app.command()
def generate(
    task: Annotated[str | None, typer.Option("--task", "-t", help="Natural-language task description.")] = None,
    target_agent: Annotated[str | None, typer.Option("--target-agent", help="codex, claude_code, chat_model, or image_model.")] = None,
    deliverable: Annotated[list[str] | None, typer.Option("--deliverable", help="Repeatable expected deliverable.")] = None,
    context: Annotated[list[str] | None, typer.Option("--context", help="Repeatable known context item.")] = None,
    file: Annotated[list[str] | None, typer.Option("--file", help="Repeatable available file path.")] = None,
    constraint: Annotated[list[str] | None, typer.Option("--constraint", help="Repeatable technical or business constraint.")] = None,
    acceptance: Annotated[list[str] | None, typer.Option("--acceptance", help="Repeatable acceptance criterion.")] = None,
    language: Annotated[Language, typer.Option("--language", help="Output language: zh-CN or en.")] = Language.ZH_CN,
    allow_staged: Annotated[bool, typer.Option("--allow-staged/--no-staging", help="Allow staged or project prompt output.")] = True,
    output: Annotated[Path | None, typer.Option("--output", help="Base directory for a unique run directory.")] = None,
) -> None:
    """Analyze a task, compile prompts, review them, and publish local artifacts."""
    interactive = task is None
    selected_target = _target(target_agent or "")
    if interactive:
        task = typer.prompt("任务描述" if language == Language.ZH_CN else "Task description")
        target_value = typer.prompt(
            "目标 AI（留空自动判断）" if language == Language.ZH_CN else "Target AI (blank to infer)",
            default="",
            show_default=False,
        )
        selected_target = _target(target_value)
        deliverable_value = typer.prompt("期望产物" if language == Language.ZH_CN else "Expected deliverables", default="", show_default=False)
        context_value = typer.prompt("已知背景" if language == Language.ZH_CN else "Known context", default="", show_default=False)
        constraint_value = typer.prompt("技术限制" if language == Language.ZH_CN else "Constraints", default="", show_default=False)
        allow_staged = typer.confirm("允许分阶段执行？" if language == Language.ZH_CN else "Allow staged execution?", default=True)
        output_value = typer.prompt("输出目录" if language == Language.ZH_CN else "Output directory", default="outputs")
        deliverable = _split(deliverable_value) or None
        context = _split(context_value) or None
        constraint = _split(constraint_value) or None
        output = Path(output_value)

        architect = PromptArchitect()
        draft, _, _ = architect.analyze(
            task,
            target_agent=selected_target,
            deliverables=deliverable,
            known_context=context,
            constraints=constraint,
            language=language,
            allow_staged=allow_staged,
        )
        if draft.has_blockers:
            answers = [typer.prompt(question) for question in draft.blocking_questions]
            task = task + "\n" + "\n".join(answers)

    architect = PromptArchitect()
    try:
        result = architect.generate(
            task or "",
            target_agent=selected_target,
            deliverables=deliverable,
            known_context=context,
            available_files=file,
            constraints=constraint,
            acceptance_criteria=acceptance,
            language=language,
            allow_staged=allow_staged,
            output_base=output,
        )
    except MissingInformationError as exc:
        console.print("[red]信息不足，未生成提示词。[/red]" if language == Language.ZH_CN else "[red]Missing information; no prompt was generated.[/red]")
        for question in exc.task.blocking_questions:
            console.print(f"- {question}")
        raise typer.Exit(code=2) from exc
    except StrategyBlockedError as exc:
        console.print(f"[red]{exc.decision.reason}[/red]")
        raise typer.Exit(code=3) from exc
    except QualityGateError as exc:
        _show_review(exc.review)
        raise typer.Exit(code=4) from exc

    decision_selected = result.task.prompt_strategy
    table = Table(title="生成完成" if language == Language.ZH_CN else "Generation Complete")
    table.add_column("项目" if language == Language.ZH_CN else "Item")
    table.add_column("结果" if language == Language.ZH_CN else "Result")
    table.add_row("任务类型" if language == Language.ZH_CN else "Task type", result.task.task_type.value)
    table.add_row("复杂度" if language == Language.ZH_CN else "Complexity", f"{result.assessment.total_score}/18")
    table.add_row("策略" if language == Language.ZH_CN else "Strategy", decision_selected.value)
    table.add_row("质量评分" if language == Language.ZH_CN else "Quality score", f"{result.review.score}/100")
    table.add_row("输出目录" if language == Language.ZH_CN else "Output directory", str(result.output_dir))
    console.print(table)


@app.command()
def analyze(
    task: Annotated[str, typer.Option("--task", "-t", help="Natural-language task description.")],
    target_agent: Annotated[str | None, typer.Option("--target-agent")] = None,
    language: Annotated[Language, typer.Option("--language")] = Language.ZH_CN,
    allow_staged: Annotated[bool, typer.Option("--allow-staged/--no-staging")] = True,
    json_output: Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")] = False,
) -> None:
    """Analyze and route a task without writing artifacts."""
    normalized, assessment, decision = PromptArchitect().analyze(
        task,
        target_agent=_target(target_agent or ""),
        language=language,
        allow_staged=allow_staged,
    )
    if json_output:
        payload = {
            "task": normalized.model_dump(mode="json"),
            "complexity": assessment.model_dump(mode="json"),
            "routing": decision.model_dump(mode="json"),
        }
        console.print_json(json.dumps(payload, ensure_ascii=False))
    else:
        _show_analysis(normalized, assessment, decision)


@app.command("review")
def review_command(
    prompt_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    language: Annotated[Language, typer.Option("--language")] = Language.ZH_CN,
) -> None:
    """Review an existing Markdown prompt without modifying it."""
    text = prompt_path.read_text(encoding="utf-8")
    result = PromptReviewer().review_text(text, language=language)
    _show_review(result)
    if not result.passed:
        raise typer.Exit(code=2)


@app.command()
def web(
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8765,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the local workbench in the default browser.")
    ] = True,
    data_dir: Annotated[
        Path | None, typer.Option("--data-dir", help="Override the local application data directory.")
    ] = None,
) -> None:
    """Start the local browser workbench on the loopback interface."""
    try:
        import uvicorn

        from prompt_architect.web.app import create_app
        from prompt_architect.web.paths import AppPaths
    except ImportError as exc:
        console.print('[red]Web dependencies are missing. Install with: pip install -e ".[web]"[/red]')
        raise typer.Exit(code=5) from exc

    paths = AppPaths.from_base(data_dir) if data_dir else AppPaths.default()
    local_url = f"http://127.0.0.1:{port}"
    if open_browser:
        import webbrowser

        Timer(0.8, lambda: webbrowser.open(local_url)).start()
    console.print(f"Prompt Architect: {local_url}")
    uvicorn.run(create_app(paths=paths), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    app()
