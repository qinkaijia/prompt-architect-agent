# Prompt Architect Agent

[![CI](https://github.com/qinkaijia/prompt-architect-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/qinkaijia/prompt-architect-agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Prompt Architect Agent 是一个本地优先的提示词架构工作台。它先分析任务类型、歧义、风险、上下文和验证难度，再选择精简、结构化、分阶段或项目任务包策略，为 Codex、Claude Code、通用聊天模型和图像模型生成可核查的提示词。

它不会调用商业模型 API，也不会扫描或上传你的仓库。

## 功能

- Windows 桌面应用，无需打开终端。
- 本地浏览器工作台与完整 CLI。
- 六维复杂度评分及逐项理由。
- 四种提示词策略和四个目标模型适配器。
- 中文默认、英文可选。
- Markdown 预览、源码查看、复制和 ZIP 下载。
- SQLite 历史搜索、归档和旧输出导入。
- 文件与目录只建立路径索引，不读取内容。
- 敏感信息脱敏、质量门禁和原子化输出。

## Windows 桌面版

从 [Releases](https://github.com/qinkaijia/prompt-architect-agent/releases) 下载：

- `Prompt-Architect-0.2.0-Setup.exe`：安装版。
- `Prompt-Architect-0.2.0-Portable.zip`：免安装便携版。

启动后数据默认保存在 `%LOCALAPPDATA%\PromptArchitect\`。应用安装后可离线使用。

## Python 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
python -m pip install -e ".[web]"
```

启动本地浏览器工作台：

```bash
python -m prompt_architect web
```

只使用 CLI：

```bash
python -m pip install -e .
python -m prompt_architect generate
```

常用命令：

```bash
python -m prompt_architect generate --task "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。"
python -m prompt_architect analyze --task "让 Codex 开发一个可切换百度和讯飞的 ASR 模块。"
python -m prompt_architect review path/to/PROMPT.md
python -m prompt_architect web --no-open --port 8765
```

## 生成物

精简和结构化任务生成 `PROMPT.md`；分阶段任务生成阶段索引和独立阶段文件；项目任务包生成：

```text
PROJECT_BRIEF.md
ARCHITECTURE_PROMPT.md
IMPLEMENTATION_PROMPT.md
TEST_PROMPT.md
REVIEW_PROMPT.md
CONTEXT_MANIFEST.md
ACCEPTANCE_CRITERIA.md
```

每次成功生成还会保存脱敏后的 `TASK_ANALYSIS.json` 和 `REVIEW_REPORT.json`。原始请求只存在于内存中。

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

架构说明见 [docs/architecture.md](docs/architecture.md)，Web 与桌面设计见 [docs/web_desktop.md](docs/web_desktop.md)，策略说明见 [docs/prompt_strategy.md](docs/prompt_strategy.md)。

## 当前边界

- 需求抽取与分类仍是确定性的规则实现。
- 不调用 Codex、Claude 或其他模型，也不启动对应进程。
- 不自动扫描仓库、读取文件内容、解析 PDF 或执行 RAG。
- 不提供云端登录、多用户、永久删除和自动更新。
- 历史记录只保存在当前设备。

## 贡献与安全

参见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。项目采用 [Apache License 2.0](LICENSE)。
