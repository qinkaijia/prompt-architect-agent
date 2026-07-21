import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const meta = {
  version: "0.2.0",
  desktop: false,
  target_agents: ["codex", "claude_code", "chat_model", "image_model"],
  languages: ["zh-CN", "en"],
  task_types: [],
  strategies: [],
};

const emptyHistory = { items: [], total: 0, limit: 30, offset: 0 };

const analysis = {
  task: {
    normalized_goal: "修改 Python 函数并增加输入检查",
    task_type: "software_development",
    target_agent: "codex",
    missing_information: [],
    risk_level: "medium",
  },
  complexity: {
    dimensions: Object.fromEntries([
      "scope",
      "dependencies",
      "ambiguity",
      "risk",
      "context_size",
      "validation_difficulty",
    ].map((key) => [key, { score: 1, reason: `${key} reason`, signals: [] }])),
    total_score: 6,
    recommended_strategy: "structured_prompt",
    reason: "中等规模任务",
  },
  routing: {
    recommended_strategy: "structured_prompt",
    selected_strategy: "structured_prompt",
    blocked: false,
    reason: "使用结构化提示词",
    warnings: [],
  },
  blockers: [],
};

const summary = {
  id: "run-1",
  created_at: "2026-07-21T10:00:00Z",
  title: "修改 Python 函数",
  normalized_goal: "修改 Python 函数并增加输入检查",
  target_agent: "codex",
  task_type: "software_development",
  strategy: "structured_prompt",
  complexity_score: 6,
  quality_score: 100,
  status: "ready",
};

const detail = {
  ...summary,
  sanitized_request: "让 Codex 修改一个 Python 函数",
  output_dir: "C:/PromptArchitect/runs/run-1",
  task: analysis.task,
  complexity: analysis.complexity,
  review: { passed: true, score: 100, issues: [], suggestions: [], repair_attempted: false },
  artifacts: [
    { filename: "PROMPT.md", media_type: "text/markdown", size: 128, download_url: "/artifact" },
  ],
};

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload),
    text: () => Promise.resolve(JSON.stringify(payload)),
  } as Response);
}

describe("Prompt Architect workbench", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/meta")) return jsonResponse(meta);
      if (url.includes("/api/v1/runs?")) return jsonResponse(emptyHistory);
      return jsonResponse({});
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the focused task form and realistic examples", async () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "把需求整理成 AI 真正能执行的任务" })).toBeInTheDocument();
    expect(screen.getByLabelText("任务描述")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /修改一个 Python 函数/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("本地运行")).toBeInTheDocument());
  });

  it("fills the request from an example without exposing advanced fields", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /科研论文风格/ }));
    expect(screen.getByLabelText("任务描述")).toHaveValue("生成一张中文科研论文风格的硬件整体连接图。");
    expect(screen.queryByLabelText("期望交付物")).not.toBeVisible();
  });

  it("validates an empty request before calling generation", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "生成提示词" }));
    expect(screen.getByRole("alert")).toHaveTextContent("请先描述");
  });

  it("shows the compact six-dimension analysis", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/meta")) return jsonResponse(meta);
      if (url.includes("/api/v1/runs?")) return jsonResponse(emptyHistory);
      if (url.includes("/api/v1/analyze")) return jsonResponse(analysis);
      return jsonResponse({});
    });
    render(<App />);
    fireEvent.change(screen.getByLabelText("任务描述"), { target: { value: "修改 Python 函数" } });
    fireEvent.click(screen.getByRole("button", { name: "分析任务" }));
    await waitFor(() => expect(screen.getByText("分析完成")).toBeInTheDocument());
    expect(screen.getByText("软件开发")).toBeInTheDocument();
    expect(screen.getAllByText("1 / 3")).toHaveLength(6);
    expect(screen.getByText("6", { selector: "dd" })).toBeInTheDocument();
  });

  it("turns missing information into answerable questions", async () => {
    const blockedAnalysis = {
      ...analysis,
      task: { ...analysis.task, missing_information: ["具体目标", "验收方式"] },
      blockers: ["需要优化哪个部分？", "如何判断优化完成？"],
    };
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/v1/meta")) return jsonResponse(meta);
      if (url.includes("/api/v1/runs?")) return jsonResponse(emptyHistory);
      if (url.endsWith("/api/v1/runs") && init?.method === "POST") {
        return jsonResponse({
          detail: {
            code: "missing_information",
            message: "请补充关键信息后再生成。",
            questions: blockedAnalysis.blockers,
            context: {},
          },
        }, 422);
      }
      if (url.includes("/api/v1/analyze")) return jsonResponse(blockedAnalysis);
      return jsonResponse({});
    });
    render(<App />);
    fireEvent.change(screen.getByLabelText("任务描述"), { target: { value: "帮我优化一下这个项目。" } });
    fireEvent.click(screen.getByRole("button", { name: "生成提示词" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "还需要一点信息" })).toBeInTheDocument());
    expect(screen.getByLabelText("需要优化哪个部分？")).toBeInTheDocument();
    expect(screen.getByLabelText("如何判断优化完成？")).toBeInTheDocument();
  });

  it("opens a history run and previews its generated Markdown", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/meta")) return jsonResponse(meta);
      if (url.includes("/api/v1/runs?")) {
        return jsonResponse({ items: [summary], total: 1, limit: 30, offset: 0 });
      }
      if (url.endsWith("/api/v1/runs/run-1")) return jsonResponse(detail);
      if (url.includes("/artifacts/PROMPT.md")) {
        return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve("# 可执行提示词\n\n正文") } as Response);
      }
      return jsonResponse({});
    });
    render(<App />);
    const historyItem = await screen.findByRole("button", { name: /修改 Python 函数/ });
    fireEvent.click(historyItem);
    await waitFor(() => expect(screen.getByRole("heading", { name: "生成结果" })).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "可执行提示词" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /PROMPT.md/ })).toBeInTheDocument();
  });
});
