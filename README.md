# Prompt Architect Agent

[![CI](https://github.com/qinkaijia/prompt-architect-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/qinkaijia/prompt-architect-agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Prompt Architect Agent is a rule-based CLI that turns a natural-language task into the smallest sufficient prompt—or prompt package—for the target AI. It analyzes task type, ambiguity, risk, context size, and validation difficulty before choosing a strategy.

提示词架构师智能体不是简单润色输入。它先标准化需求、解释复杂度、选择合适粒度，再为 Codex、Claude Code、通用聊天模型或图像模型编译可核查的提示词。

## Features

- Four strategies: compact, structured, staged, and project prompt package.
- Six explainable complexity dimensions with YAML-configured signals.
- Codex, Claude Code, chat model, and image model adapters.
- Chinese output by default, with English templates available.
- Context manifests that index files without bulk-reading repositories or PDFs.
- A quality gate for missing deliverables, conflicts, secrets, fabricated execution, unverifiable claims, and broad repository changes.
- Atomic, non-overwriting Markdown and JSON output.
- No external model or commercial API calls.

## Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## CLI

Interactive generation:

```bash
python -m prompt_architect generate
```

Generate from one task:

```bash
python -m prompt_architect generate \
  --task "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。"
```

Analyze without writing files:

```bash
python -m prompt_architect analyze \
  --task "让 Codex 开发一个可切换百度和讯飞的 ASR 模块。"
```

Review an existing prompt:

```bash
python -m prompt_architect review path/to/PROMPT.md
```

Useful options:

```text
--target-agent codex|claude_code|chat_model|image_model
--language zh-CN|en
--output PATH
--allow-staged / --no-staging
--deliverable TEXT
--context TEXT
--file PATH
--constraint TEXT
--acceptance TEXT
```

Repeat list options to provide multiple values. `--output` is a base directory; each successful run creates a unique `<task-type>-<timestamp>/` child directory.

## Output

Compact and structured tasks create `PROMPT.md`. Staged tasks create `STAGE_INDEX.md` and individual stage prompts. Project-level tasks create:

```text
PROJECT_BRIEF.md
ARCHITECTURE_PROMPT.md
IMPLEMENTATION_PROMPT.md
TEST_PROMPT.md
REVIEW_PROMPT.md
CONTEXT_MANIFEST.md
ACCEPTANCE_CRITERIA.md
```

Every successful run also writes `TASK_ANALYSIS.json` and `REVIEW_REPORT.json`. The original request is kept in memory only; persisted analysis contains the secret-redacted request.

## Strategy thresholds

| Score | Strategy |
|---:|---|
| 0–4 | `compact_prompt` |
| 5–8 | `structured_prompt` |
| 9–13 | `staged_prompt` |
| 14–18 | `project_prompt_package` |

The six dimensions are scope, dependencies, ambiguity, risk, context size, and validation difficulty. Each dimension is scored from 0 to 3 with matched signals and a human-readable reason.

## Architecture

```text
Request → Analyzer → Classifier → Missing-info gate → Complexity scorer
        → Strategy router → Context manager → Model adapter → Jinja compiler
        → Prompt reviewer → Atomic publisher
```

See [architecture](docs/architecture.md), [prompt strategy](docs/prompt_strategy.md), and [roadmap](docs/development_roadmap.md) for details.

## Current limitations

- Requirement extraction is deterministic and keyword-based; it is intentionally not an LLM parser.
- Repository paths are indexed but the repository is not scanned automatically.
- PDF and datasheet content is not extracted.
- Feedback learning, persistence, RAG, web UI, and model API integrations are outside the MVP.
- Rule classification is transparent but will not understand every paraphrase.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow. Do not include credentials in tasks or generated prompt fixtures; report security issues according to [SECURITY.md](SECURITY.md).

## License

Licensed under the [Apache License 2.0](LICENSE).
