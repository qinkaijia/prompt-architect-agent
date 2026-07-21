# Prompt Architect Agent

[![CI](https://github.com/qinkaijia/prompt-architect-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/qinkaijia/prompt-architect-agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Prompt Architect Agent 是一个本地优先的提示词智能体。它使用 DeepSeek 理解需求、按需追问、选择任务粒度、生成提示词，并通过模型评审和确定性规则进行双重质量检查。

它只生成提示词，不会自动执行 Codex、Claude Code 或用户任务。

## v0.3.0 功能

- DeepSeek 智能分析、生成、评审和一次自动修复。
- 信息充分时直接生成，关键上下文不足时最多追问三轮。
- Windows 首次配置引导，密钥验证成功后保存到系统凭据库。
- 支持 Codex、Claude Code、聊天模型和图像模型的提示词适配。
- 精简、结构化、分阶段和项目任务包四种策略。
- 用户授权后读取代码、文本及可提取文字的 PDF。
- 脱敏会话历史、Token 用量、Markdown 预览和 ZIP 下载。
- 不连接模型的规则离线模式和原有 CLI。

## Windows 桌面版

从 [Releases](https://github.com/qinkaijia/prompt-architect-agent/releases) 下载：

- `Prompt-Architect-0.3.0-Setup.exe`：安装版。
- `Prompt-Architect-0.3.0-Portable.zip`：免安装便携版。

首次启动：

1. 在应用内点击“打开 DeepSeek 密钥页面”并创建密钥。
2. 将密钥粘贴到本机设置界面，点击“保存并连接”。
3. 选择“自动选择模型”，然后开始智能生成。

请勿把 API Key 发送到聊天、截图或代码仓库。DeepSeek API 独立计费；连接验证只读取模型列表，不产生模型生成费用。

密钥由 Windows Credential Manager 保存，也可以通过 `DEEPSEEK_API_KEY` 环境变量提供。应用不会把密钥写入 SQLite、日志或生成文件。

应用数据默认保存在 `%LOCALAPPDATA%\PromptArchitect\`。

## Python 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
python -m pip install -e ".[web]"
python -m prompt_architect web
```

CLI 保持规则离线生成：

```bash
python -m prompt_architect generate --task "让 Codex 修改一个 Python 函数并增加输入检查。"
python -m prompt_architect analyze --task "让 Codex 开发一个 ASR 模块。"
python -m prompt_architect review path/to/PROMPT.md
```

## 智能体流程

```text
用户需求
  → DeepSeek 结构化理解
  → 必要时针对性追问
  → 读取明确授权的上下文
  → 按复杂度生成提示词文件
  → DeepSeek 独立评审 + 本地安全规则
  → 最多一次自动修复
  → 原子发布 Markdown / JSON
```

精简和结构化任务生成 `PROMPT.md`；分阶段任务生成阶段索引和独立阶段文件；项目任务包生成约定的七个 Markdown 文件。每次成功生成还会保存脱敏后的 `TASK_ANALYSIS.json` 和 `REVIEW_REPORT.json`。

## 隐私与上下文

- 只有用户在当前任务中选择的文件才会读取并发送给 DeepSeek。
- 桌面目录只建立索引，不会递归扫描。
- 浏览器上传存放在会话临时目录，任务结束后删除。
- 支持常见源代码、TXT、Markdown、JSON、YAML、TOML 和文本型 PDF。
- 扫描版 PDF 不执行 OCR，会给出明确提示。
- 上下文发送前执行常见密钥模式脱敏，并受文件数量、大小和上下文预算限制。
- 不保存模型隐藏推理、原始文件内容或提供商原始响应。

## 开发

```bash
python -m pip install -e ".[web,dev]"
python -m pytest

cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

架构见 [docs/architecture.md](docs/architecture.md)，桌面设计见 [docs/web_desktop.md](docs/web_desktop.md)，策略见 [docs/prompt_strategy.md](docs/prompt_strategy.md)。

## 当前边界

- v0.3.0 只接入 DeepSeek，不接入 OpenAI 或 Kimi。
- 不自动执行生成的提示词，不启动目标智能体。
- 不递归扫描仓库，不提供 RAG、OCR、联网搜索或云端账号。
- 未完成的智能会话在应用重启后需要重新开始并重新授权文件。
- 历史记录只保存在当前设备。

## 贡献与安全

参见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。项目采用 [Apache License 2.0](LICENSE)。
