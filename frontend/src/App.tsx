import {
  Archive,
  BrainCircuit,
  Check,
  ChevronDown,
  Clipboard,
  Copy,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FilePlus2,
  Files,
  FolderOpen,
  History,
  KeyRound,
  Menu,
  PanelRight,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, ApiClientError } from "./api";
import type {
  AgentEvent,
  AnalysisResponse,
  GenerationRequest,
  MetaResponse,
  ProviderStatus,
  RunDetail,
  RunSummary,
  TargetAgent,
} from "./types";

const AGENT_LABELS: Record<string, string> = {
  codex: "Codex",
  claude_code: "Claude Code",
  chat_model: "通用聊天模型",
  image_model: "图像模型",
};

const STRATEGY_LABELS: Record<string, string> = {
  compact_prompt: "精简提示词",
  structured_prompt: "结构化提示词",
  staged_prompt: "分阶段提示词",
  project_prompt_package: "项目任务包",
};

const TASK_LABELS: Record<string, string> = {
  software_development: "软件开发",
  code_debugging: "代码调试",
  repository_refactoring: "仓库重构",
  embedded_system: "嵌入式系统",
  hardware_design: "硬件设计",
  simulation: "仿真",
  research: "科研分析",
  document_writing: "文档写作",
  data_analysis: "数据分析",
  image_design: "图像设计",
  presentation: "演示文稿",
  automation: "自动化",
  agent_development: "智能体开发",
  learning: "学习",
  general: "通用任务",
};

const DIMENSIONS = [
  ["scope", "任务范围"],
  ["dependencies", "文件依赖"],
  ["ambiguity", "需求歧义"],
  ["risk", "技术风险"],
  ["context_size", "上下文体量"],
  ["validation_difficulty", "验证难度"],
] as const;

const EXAMPLES = [
  "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。",
  "让 Codex 在现有 Python 项目中开发一个可切换百度和讯飞的 ASR 模块。",
  "生成一张中文科研论文风格的硬件整体连接图。",
];

interface FormState {
  rawRequest: string;
  targetAgent: "" | TargetAgent;
  language: "zh-CN" | "en";
  allowStaged: boolean;
  deliverables: string;
  knownContext: string;
  constraints: string;
  forbiddenActions: string;
  tools: string;
  acceptanceCriteria: string;
}

const EMPTY_FORM: FormState = {
  rawRequest: "",
  targetAgent: "",
  language: "zh-CN",
  allowStaged: true,
  deliverables: "",
  knownContext: "",
  constraints: "",
  forbiddenActions: "",
  tools: "",
  acceptanceCriteria: "",
};

const splitLines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

function payloadFrom(form: FormState, paths: string[]): GenerationRequest {
  return {
    raw_request: form.rawRequest.trim(),
    ...(form.targetAgent ? { target_agent: form.targetAgent } : {}),
    deliverables: splitLines(form.deliverables),
    known_context: splitLines(form.knownContext),
    available_files: paths,
    constraints: splitLines(form.constraints),
    forbidden_actions: splitLines(form.forbiddenActions),
    tools: splitLines(form.tools),
    acceptance_criteria: splitLines(form.acceptanceCriteria),
    language: form.language,
    allow_staged: form.allowStaged,
  };
}

function App() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [paths, setPaths] = useState<string[]>([]);
  const [pathDraft, setPathDraft] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState("");
  const [artifactContent, setArtifactContent] = useState("");
  const [previewMode, setPreviewMode] = useState<"rendered" | "source">("rendered");
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyStatus, setHistoryStatus] = useState("ready");
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [busy, setBusy] = useState<"analyze" | "generate" | "">("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [blockers, setBlockers] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [historyOpen, setHistoryOpen] = useState(false);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [providerLoaded, setProviderLoaded] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [offlineMode, setOfflineMode] = useState(false);
  const [contextGrants, setContextGrants] = useState<string[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [agentStage, setAgentStage] = useState("");

  const refreshHistory = useCallback(async () => {
    try {
      const result = await api.history(historyQuery, historyStatus);
      setHistory(result.items);
    } catch {
      setError("历史记录暂时无法读取。");
    }
  }, [historyQuery, historyStatus]);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setError("无法连接本地服务。"));
    api.provider()
      .then(setProvider)
      .catch(() => setError("无法读取 DeepSeek 设置。"))
      .finally(() => setProviderLoaded(true));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(refreshHistory, 180);
    return () => window.clearTimeout(timer);
  }, [refreshHistory]);

  const addPaths = (newPaths: string[]) => {
    setPaths((current) => Array.from(new Set([...current, ...newPaths.filter(Boolean)])));
  };

  const chooseFiles = async () => {
    if (window.pywebview) {
      const selected = await window.pywebview.api.choose_files();
      if (selected.length) {
        const grant = await api.grantDesktop(selected);
        addPaths(grant.files.map((item) => item.name));
        setContextGrants((current) => [...current, grant.id]);
      }
    }
  };

  const chooseDirectory = async () => {
    if (window.pywebview) {
      const chosen = await window.pywebview.api.choose_directory();
      if (chosen) {
        const grant = await api.grantDesktop([chosen]);
        addPaths(grant.files.map((item) => item.name));
        setContextGrants((current) => [...current, grant.id]);
      }
    }
  };

  const uploadFiles = async (files: File[]) => {
    if (!files.length) return;
    try {
      const grant = await api.uploadContext(files);
      addPaths(grant.files.map((item) => item.name));
      setContextGrants((current) => [...current, grant.id]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "文件授权失败。");
    }
  };

  const runAnalysis = async (payload = payloadFrom(form, paths)) => {
    if (!payload.raw_request) {
      setError("请先描述你希望 AI 完成的任务。");
      return null;
    }
    setBusy("analyze");
    setError("");
    setNotice("");
    try {
      const result = await api.analyze(payload);
      setAnalysis(result);
      setBlockers(result.blockers);
      setAnswers({});
      setAnalysisOpen(true);
      return result;
    } catch {
      setError("任务分析失败，请检查输入后重试。");
      return null;
    } finally {
      setBusy("");
    }
  };

  const loadArtifact = useCallback(async (runId: string, filename: string) => {
    setSelectedArtifact(filename);
    try {
      setArtifactContent(await api.artifact(runId, filename));
    } catch {
      setError("生成文件暂时无法读取。");
    }
  }, []);

  const openRun = useCallback(
    async (summary: RunSummary | RunDetail) => {
      setError("");
      try {
        const run = "artifacts" in summary ? summary : await api.run(summary.id);
        setSelectedRun(run);
        setAnalysis(null);
        setHistoryOpen(false);
        const preferred = run.artifacts.find((item) => item.filename.endsWith(".md"));
        if (preferred) await loadArtifact(run.id, preferred.filename);
      } catch {
        setError("无法打开该历史记录。");
      }
    },
    [loadArtifact],
  );

  const handleAgentEvent = (event: AgentEvent) => {
    if (event.event === "stage.started") {
      setAgentStage(String(event.data.message ?? "正在处理…"));
    } else if (event.event === "analysis.completed") {
      setAnalysis(event.data.analysis as unknown as AnalysisResponse);
      setAnalysisOpen(true);
    } else if (event.event === "questions.required") {
      setBlockers((event.data.questions as string[]) ?? []);
      setAnswers({});
      setAgentStage("");
    } else if (event.event === "failed") {
      setError(String(event.data.message ?? "智能生成失败，请重试。"));
      setAgentStage("");
      setActiveSession(null);
    }
  };

  const continueAgent = async (sessionId: string, turnAnswers: string[]) => {
    let published: RunDetail | null = null;
    let completionNote = "提示词已由 DeepSeek 生成，并通过双重质量检查。";
    await api.agentTurn(sessionId, turnAnswers, (event) => {
      handleAgentEvent(event);
      if (event.event === "run.published") {
        published = event.data.run as unknown as RunDetail;
        const usage = event.data.usage as { total_tokens?: number } | undefined;
        const model = String(event.data.model ?? "DeepSeek");
        completionNote = `生成完成 · ${model} · ${usage?.total_tokens ?? 0} Token · 已通过双重质量检查`;
      }
    });
    if (published) {
      setBlockers([]);
      setActiveSession(null);
      setAgentStage("");
      setNotice(completionNote);
      await openRun(published);
      await refreshHistory();
    }
  };

  const generate = async () => {
    const payload = payloadFrom(form, paths);
    if (!payload.raw_request) {
      setError("请先描述你希望 AI 完成的任务。");
      return;
    }
    setBusy("generate");
    setError("");
    setNotice("");
    try {
      if (offlineMode) {
        const run = await api.generate(payload);
        setBlockers([]);
        setNotice("提示词已通过规则离线生成。");
        await openRun(run);
        await refreshHistory();
      } else {
        if (!provider?.configured) {
          setSettingsOpen(true);
          throw new Error("请先连接 DeepSeek。");
        }
        const session = await api.createAgentSession({
          ...payload,
          model_id: provider.default_model || "auto",
          offline_rules: false,
          context_grants: contextGrants,
        });
        setActiveSession(session.id);
        await continueAgent(session.id, []);
      }
    } catch (caught) {
      if (caught instanceof ApiClientError && caught.detail.code === "missing_information") {
        setBlockers(caught.detail.questions);
        await runAnalysis(payload);
      } else if (caught instanceof ApiClientError) {
        setError(caught.detail.message);
      } else {
        setError("生成失败，请稍后重试。");
      }
    } finally {
      setBusy("");
    }
  };

  const completeBlockers = async () => {
    const values = blockers.map((_, index) => answers[index]?.trim() ?? "");
    if (values.some((item) => !item)) {
      setError("请回答所有补充问题。");
      return;
    }
    if (activeSession) {
      setBusy("generate");
      setError("");
      try {
        await continueAgent(activeSession, values);
      } finally {
        setBusy("");
      }
      return;
    }
    const additions = blockers.map((question, index) => `${question} ${values[index]}`);
    const next = {
      ...form,
      rawRequest: `${form.rawRequest.trim()}\n\n补充信息：\n${additions.join("\n")}`,
    };
    setForm(next);
    await runAnalysis(payloadFrom(next, paths));
  };

  const newTask = () => {
    setForm(EMPTY_FORM);
    setPaths([]);
    setContextGrants([]);
    setAnalysis(null);
    setSelectedRun(null);
    setSelectedArtifact("");
    setArtifactContent("");
    setBlockers([]);
    setNotice("");
    setError("");
    setHistoryOpen(false);
    setActiveSession(null);
    setAgentStage("");
  };

  const cancelAgent = async () => {
    if (!activeSession) return;
    await api.cancelAgent(activeSession);
    setActiveSession(null);
    setBusy("");
    setAgentStage("");
    setNotice("已取消智能生成。");
  };

  const archiveCurrent = async () => {
    if (!selectedRun) return;
    await api.archive(selectedRun.id);
    setNotice("记录已归档，生成文件仍保留在本地。");
    setSelectedRun(null);
    await refreshHistory();
  };

  const importHistory = async () => {
    let source: string | null = null;
    if (window.pywebview) source = await window.pywebview.api.choose_directory();
    else source = window.prompt("请输入旧版 outputs 目录的完整路径：");
    if (!source) return;
    try {
      const result = await api.importHistory(source);
      setNotice(`已导入 ${result.imported} 条历史记录。`);
      await refreshHistory();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "历史记录导入失败。");
    }
  };

  const currentAnalysis = useMemo(() => {
    if (analysis) return analysis;
    if (!selectedRun) return null;
    return {
      task: selectedRun.task as AnalysisResponse["task"],
      complexity: selectedRun.complexity,
      routing: {
        recommended_strategy: selectedRun.strategy,
        selected_strategy: selectedRun.strategy,
        blocked: false,
        reason: "该记录已生成并通过质量检查。",
        warnings: [],
      },
      blockers: [],
    } satisfies AnalysisResponse;
  }, [analysis, selectedRun]);

  if (!providerLoaded) {
    return <div className="setup-loading"><span className="spinner" /><p>正在准备 Prompt Architect…</p></div>;
  }

  if (!provider?.configured && !offlineMode) {
    return <ProviderSetup
      version={meta?.version ?? "0.3.0"}
      onConnected={setProvider}
      onOffline={() => setOfflineMode(true)}
    />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="icon-button mobile-only"
          type="button"
          aria-label="打开历史记录"
          onClick={() => setHistoryOpen(true)}
        >
          <Menu aria-hidden="true" />
        </button>
        <div className="brand" aria-label="Prompt Architect">
          <BrainCircuit aria-hidden="true" />
          <span>Prompt Architect</span>
          <span className="version">v{meta?.version ?? "0.3.0"}</span>
        </div>
        <div className="topbar-actions">
          <button className={`provider-pill ${offlineMode ? "is-offline" : ""}`} type="button" onClick={() => setSettingsOpen(true)}>
            {offlineMode ? <><span className="status-dot" /> 规则离线</> : <><span className="status-dot" /> DeepSeek {provider?.key_hint}</>}
          </button>
          <button className="icon-button" type="button" aria-label="打开模型设置" onClick={() => setSettingsOpen(true)}><Settings aria-hidden="true" /></button>
          <button
            className="icon-button analysis-toggle"
            type="button"
            aria-label="打开任务分析"
            onClick={() => setAnalysisOpen(true)}
          >
            <PanelRight aria-hidden="true" />
          </button>
        </div>
      </header>

      <aside className={`history-panel ${historyOpen ? "is-open" : ""}`} aria-label="历史记录">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">工作区</span>
            <h2>最近任务</h2>
          </div>
          <button className="icon-button mobile-only" type="button" aria-label="关闭历史记录" onClick={() => setHistoryOpen(false)}>
            <X aria-hidden="true" />
          </button>
        </div>
        <button className="button primary full" type="button" onClick={newTask}>
          <Plus aria-hidden="true" /> 新建任务
        </button>
        <label className="search-field">
          <Search aria-hidden="true" />
          <span className="sr-only">搜索历史记录</span>
          <input value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="搜索任务" />
        </label>
        <label className="compact-select">
          <span className="sr-only">历史记录状态</span>
          <select value={historyStatus} onChange={(event) => setHistoryStatus(event.target.value)}>
            <option value="ready">最近生成</option>
            <option value="archived">已归档</option>
            <option value="all">全部记录</option>
          </select>
          <ChevronDown aria-hidden="true" />
        </label>
        <div className="history-list">
          {history.length ? history.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`history-item ${selectedRun?.id === item.id ? "is-selected" : ""}`}
              onClick={() => openRun(item)}
            >
              <span>{item.title}</span>
              <small>{AGENT_LABELS[item.target_agent]} · {new Date(item.created_at).toLocaleDateString()}</small>
            </button>
          )) : <p className="panel-empty">还没有匹配的记录</p>}
        </div>
        <button className="button ghost full import-button" type="button" onClick={importHistory}>
          <History aria-hidden="true" /> 导入旧记录
        </button>
      </aside>

      <main className="workspace">
        <section className="workspace-intro">
          <div>
            <span className="eyebrow">提示词工作台</span>
            <h1>把想法交给智能体，得到真正可执行的提示词</h1>
            <p>{offlineMode ? "当前使用规则离线模式，不会连接外部模型。" : "DeepSeek 会理解需求、按需追问并独立检查生成结果。"}</p>
          </div>
        </section>

        {error && <div className="message error" role="alert">{error}</div>}
        {notice && <div className="message success" role="status"><Check aria-hidden="true" /> {notice}</div>}

        <section className="surface task-surface" aria-labelledby="task-title">
          <div className="section-heading">
            <div>
              <h2 id="task-title">描述任务</h2>
              <p>说明目标、对象和希望得到的结果。</p>
            </div>
            <FilePlus2 aria-hidden="true" />
          </div>
          <label className="field">
            <span>任务描述</span>
            <textarea
              value={form.rawRequest}
              onChange={(event) => setForm({ ...form, rawRequest: event.target.value })}
              placeholder="例如：让 Codex 在现有 Python 项目中开发一个支持多供应商的 ASR 模块……"
              rows={6}
            />
          </label>

          {!form.rawRequest && (
            <div className="examples" aria-label="示例任务">
              <span>试试这些示例</span>
              {EXAMPLES.map((example) => (
                <button key={example} type="button" onClick={() => setForm({ ...form, rawRequest: example })}>
                  {example}
                </button>
              ))}
            </div>
          )}

          <div className="quick-fields">
            <label className="field">
              <span>目标 AI</span>
              <select value={form.targetAgent} onChange={(event) => setForm({ ...form, targetAgent: event.target.value as FormState["targetAgent"] })}>
                <option value="">自动判断</option>
                <option value="codex">Codex</option>
                <option value="claude_code">Claude Code</option>
                <option value="chat_model">通用聊天模型</option>
                <option value="image_model">图像模型</option>
              </select>
            </label>
            <label className="field">
              <span>输出语言</span>
              <select value={form.language} onChange={(event) => setForm({ ...form, language: event.target.value as FormState["language"] })}>
                <option value="zh-CN">中文</option>
                <option value="en">English</option>
              </select>
            </label>
            <label className="switch-field">
              <input type="checkbox" checked={form.allowStaged} onChange={(event) => setForm({ ...form, allowStaged: event.target.checked })} />
              <span><strong>允许分阶段</strong><small>复杂任务自动拆分</small></span>
            </label>
          </div>

          <details className="advanced">
            <summary>高级设置 <span>上下文、交付物和约束</span></summary>
            <div className="advanced-grid">
              <TextAreaField label="期望交付物" value={form.deliverables} onChange={(value) => setForm({ ...form, deliverables: value })} placeholder="每行一项" />
              <TextAreaField label="已知背景" value={form.knownContext} onChange={(value) => setForm({ ...form, knownContext: value })} placeholder="每行一项" />
              <TextAreaField label="技术与业务限制" value={form.constraints} onChange={(value) => setForm({ ...form, constraints: value })} placeholder="每行一项" />
              <TextAreaField label="禁止事项" value={form.forbiddenActions} onChange={(value) => setForm({ ...form, forbiddenActions: value })} placeholder="每行一项" />
              <TextAreaField label="可用工具" value={form.tools} onChange={(value) => setForm({ ...form, tools: value })} placeholder="每行一项" />
              <TextAreaField label="验收标准" value={form.acceptanceCriteria} onChange={(value) => setForm({ ...form, acceptanceCriteria: value })} placeholder="每行一项" />
            </div>
            <div className="context-picker">
              <div>
                <strong>上下文路径</strong>
                <p>{offlineMode ? "离线模式只建立路径索引。" : "只有你在这里选择的文件才会发送给 DeepSeek。"}</p>
              </div>
              <div className="path-actions">
                {meta?.desktop && <>
                  <button className="button ghost" type="button" onClick={chooseFiles}><Files aria-hidden="true" /> 选择文件</button>
                  <button className="button ghost" type="button" onClick={chooseDirectory}><FolderOpen aria-hidden="true" /> 选择目录</button>
                </>}
                {!meta?.desktop && !offlineMode && <label className="button ghost file-upload"><Files aria-hidden="true" /> 选择文件<input type="file" multiple onChange={(event) => uploadFiles(Array.from(event.target.files ?? []))} /></label>}
              </div>
              {offlineMode && <div className="manual-path">
                <input value={pathDraft} onChange={(event) => setPathDraft(event.target.value)} placeholder="输入文件或目录路径" />
                <button className="button ghost" type="button" onClick={() => { addPaths([pathDraft.trim()]); setPathDraft(""); }}>添加</button>
              </div>}
              {!!paths.length && <div className="path-list">
                {paths.map((path) => <span key={path}><code>{path}</code><button type="button" aria-label={`移除 ${path}`} onClick={() => setPaths(paths.filter((item) => item !== path))}><X aria-hidden="true" /></button></span>)}
              </div>}
            </div>
          </details>

          <div className="task-actions">
            <button className="button secondary" type="button" disabled={!!busy} onClick={() => runAnalysis()}>
              {busy === "analyze" ? <span className="spinner" /> : <BrainCircuit aria-hidden="true" />} 分析任务
            </button>
            <button className="button primary" type="button" disabled={!!busy} onClick={generate}>
              {busy === "generate" ? <span className="spinner" /> : <Sparkles aria-hidden="true" />} {offlineMode ? "离线生成" : "智能生成"}
            </button>
            {busy === "generate" && activeSession && <button className="button ghost" type="button" onClick={cancelAgent}>取消</button>}
          </div>
        </section>

        {agentStage && <div className="agent-progress" role="status"><span className="spinner" /><span>{agentStage}</span><small>不会显示虚假的完成百分比</small></div>}

        {!!blockers.length && (
          <section className="surface blockers" aria-labelledby="blocker-title">
            <div className="section-heading">
              <div><h2 id="blocker-title">还需要一点信息</h2><p>回答后会自动重新分析任务。</p></div>
            </div>
            {blockers.map((question, index) => (
              <label className="field" key={question}>
                <span>{question}</span>
                <input value={answers[index] ?? ""} onChange={(event) => setAnswers({ ...answers, [index]: event.target.value })} />
              </label>
            ))}
            <button className="button primary" type="button" onClick={completeBlockers}>{activeSession ? "回答并继续生成" : "补充并重新分析"}</button>
          </section>
        )}

        {selectedRun ? (
          <ResultWorkspace
            run={selectedRun}
            selectedArtifact={selectedArtifact}
            content={artifactContent}
            previewMode={previewMode}
            desktop={Boolean(meta?.desktop)}
            onSelect={(filename) => loadArtifact(selectedRun.id, filename)}
            onMode={setPreviewMode}
            onArchive={archiveCurrent}
          />
        ) : analysis ? (
          <section className="analysis-ready" aria-live="polite">
            <BrainCircuit aria-hidden="true" />
            <div><strong>分析完成</strong><span>{STRATEGY_LABELS[analysis.routing.selected_strategy ?? analysis.routing.recommended_strategy]}适合这项任务。</span></div>
          </section>
        ) : (
          <section className="empty-result">
            <Clipboard aria-hidden="true" />
            <h2>生成结果会出现在这里</h2>
            <p>你可以先分析任务，确认复杂度和推荐策略。</p>
          </section>
        )}
      </main>

      <aside className={`analysis-panel ${analysisOpen ? "is-open" : ""}`} aria-label="任务分析">
        <div className="panel-heading">
          <div><span className="eyebrow">实时判断</span><h2>任务分析</h2></div>
          <button className="icon-button analysis-toggle" type="button" aria-label="关闭任务分析" onClick={() => setAnalysisOpen(false)}><X aria-hidden="true" /></button>
        </div>
        <AnalysisPanel analysis={currentAnalysis} />
      </aside>

      {settingsOpen && <ProviderSettings
        provider={provider}
        offlineMode={offlineMode}
        onProvider={setProvider}
        onOffline={setOfflineMode}
        onClose={() => setSettingsOpen(false)}
      />}

      {(historyOpen || analysisOpen || settingsOpen) && <button className="scrim" type="button" aria-label="关闭侧栏" onClick={() => { setHistoryOpen(false); setAnalysisOpen(false); setSettingsOpen(false); }} />}
    </div>
  );
}

function ProviderSetup({ version, onConnected, onOffline }: {
  version: string;
  onConnected: (status: ProviderStatus) => void;
  onOffline: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const connect = async () => {
    const normalized = apiKey.trim();
    if (!normalized) {
      setError("请粘贴新创建的 DeepSeek API Key。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const status = await api.saveCredential(normalized);
      setApiKey("");
      onConnected(status);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "连接失败，请检查密钥后重试。");
    } finally {
      setBusy(false);
    }
  };

  return <main className="setup-shell">
    <header className="setup-brand"><BrainCircuit aria-hidden="true" /><span>Prompt Architect</span><small>v{version}</small></header>
    <section className="setup-card" aria-labelledby="setup-title">
      <div className="setup-heading">
        <span className="setup-icon"><KeyRound aria-hidden="true" /></span>
        <div><span className="eyebrow">只需设置一次</span><h1 id="setup-title">连接 DeepSeek，开始智能生成</h1><p>密钥只保存在这台电脑的系统凭据库中，不会写入历史记录或生成文件。</p></div>
      </div>
      <ol className="setup-steps">
        <li><span>1</span><div><strong>创建新密钥</strong><p>刚才发到聊天里的旧密钥需要先撤销，再创建一个新的。</p><a className="text-link" href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer">打开 DeepSeek 密钥页面 <ExternalLink aria-hidden="true" /></a></div></li>
        <li><span>2</span><div><strong>粘贴到这里</strong><p>请不要把新密钥发送到聊天、截图或代码仓库。</p><div className="secret-input"><input autoFocus value={apiKey} onChange={(event) => setApiKey(event.target.value)} type={showKey ? "text" : "password"} placeholder="粘贴 DeepSeek API Key" aria-label="DeepSeek API Key" autoComplete="off" spellCheck={false} /><button type="button" aria-label={showKey ? "隐藏密钥" : "显示密钥"} onClick={() => setShowKey(!showKey)}>{showKey ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}</button>{apiKey && <button type="button" aria-label="清空密钥" onClick={() => setApiKey("")}><X aria-hidden="true" /></button>}</div></div></li>
        <li><span>3</span><div><strong>保存并连接</strong><p>应用会先验证连接，成功后才安全保存，不会产生模型生成费用。</p></div></li>
      </ol>
      {error && <div className="message error" role="alert">{error}<span>密钥无效时请重新复制；余额不足可前往 <a href="https://platform.deepseek.com/top_up" target="_blank" rel="noreferrer">DeepSeek 充值</a>。</span></div>}
      <button className="button primary setup-primary" type="button" disabled={busy} onClick={connect}>{busy ? <span className="spinner" /> : <ShieldCheck aria-hidden="true" />} 保存并连接</button>
      <button className="button ghost setup-offline" type="button" onClick={onOffline}>暂时使用规则离线模式</button>
    </section>
  </main>;
}

function ProviderSettings({ provider, offlineMode, onProvider, onOffline, onClose }: {
  provider: ProviderStatus | null;
  offlineMode: boolean;
  onProvider: (status: ProviderStatus) => void;
  onOffline: (value: boolean) => void;
  onClose: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [models, setModels] = useState(provider?.models ?? []);
  const [model, setModel] = useState(provider?.default_model ?? "auto");

  const test = async () => {
    setBusy("test"); setError(""); setMessage("");
    try {
      const status = await api.testProvider();
      setModels(status.models); onProvider(status); setMessage("连接正常，可以智能生成。");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "连接测试失败。"); }
    finally { setBusy(""); }
  };
  const replace = async () => {
    if (!apiKey.trim()) { setError("请先粘贴新的 API Key。"); return; }
    setBusy("save"); setError("");
    try {
      const status = await api.saveCredential(apiKey.trim());
      setApiKey(""); setEditing(false); setModels(status.models); onProvider(status); onOffline(false); setMessage("新密钥已安全保存。");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "保存失败。"); }
    finally { setBusy(""); }
  };
  const remove = async () => {
    setBusy("remove"); setError("");
    try { const status = await api.deleteCredential(); onProvider(status); onOffline(true); setMessage("密钥已从系统凭据库移除。"); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "无法移除密钥。"); }
    finally { setBusy(""); }
  };
  const selectModel = async (value: string) => {
    setModel(value); setError("");
    try { await api.setDefaultModel(value); if (provider) onProvider({ ...provider, default_model: value }); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "模型设置失败。"); }
  };

  return <aside className="settings-drawer" aria-label="DeepSeek 设置">
    <div className="settings-header"><div><span className="eyebrow">模型连接</span><h2>DeepSeek 设置</h2></div><button className="icon-button" type="button" aria-label="关闭设置" onClick={onClose}><X aria-hidden="true" /></button></div>
    <div className={`connection-card ${offlineMode ? "is-offline" : ""}`}><span className="connection-icon"><ShieldCheck aria-hidden="true" /></span><div><strong>{offlineMode ? "规则离线模式" : provider?.configured ? "DeepSeek 已配置" : "尚未连接"}</strong><p>{offlineMode ? "不会把任务发送给外部模型。" : provider?.source === "environment" ? "由 DEEPSEEK_API_KEY 环境变量管理" : `${provider?.key_hint ?? ""} · 保存在 Windows 系统凭据库`}</p></div></div>
    {message && <div className="message success" role="status"><Check aria-hidden="true" /> {message}</div>}
    {error && <div className="message error" role="alert">{error}</div>}
    {provider?.configured && <>
      <label className="field"><span>默认模型</span><select value={model} onChange={(event) => selectModel(event.target.value)}><option value="auto">自动选择（推荐）</option>{models.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}</select><small>智能生成完成后会显示实际使用的模型。</small></label>
      <button className="button secondary full" type="button" disabled={!!busy} onClick={test}>{busy === "test" ? <span className="spinner" /> : <ShieldCheck aria-hidden="true" />} 测试连接</button>
    </>}
    {!provider?.configured && !editing && <button className="button primary full settings-connect" type="button" onClick={() => setEditing(true)}><KeyRound aria-hidden="true" /> 连接 DeepSeek</button>}
    {editing && <div className="replace-key"><label className="field"><span>新的 API Key</span><div className="secret-input"><input value={apiKey} onChange={(event) => setApiKey(event.target.value)} type={showKey ? "text" : "password"} autoComplete="off" spellCheck={false} /><button type="button" aria-label={showKey ? "隐藏密钥" : "显示密钥"} onClick={() => setShowKey(!showKey)}>{showKey ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}</button></div></label><button className="button primary full" type="button" disabled={!!busy} onClick={replace}>{busy === "save" ? <span className="spinner" /> : <ShieldCheck aria-hidden="true" />} 保存并连接</button></div>}
    <div className="settings-actions">
      {provider?.configured && provider.source !== "environment" && <button className="button ghost full" type="button" onClick={() => setEditing(!editing)}>{editing ? "取消更换" : "更换密钥"}</button>}
      {!provider?.configured && editing && <button className="button ghost full" type="button" onClick={() => { setEditing(false); setApiKey(""); }}>取消</button>}
      {provider?.configured && provider.source !== "environment" && <button className="button danger full" type="button" disabled={!!busy} onClick={remove}>移除密钥</button>}
      {provider?.configured && <button className="button ghost full" type="button" onClick={() => onOffline(!offlineMode)}>{offlineMode ? "切回 DeepSeek 智能模式" : "切换为规则离线模式"}</button>}
      <a className="text-link" href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer">管理 DeepSeek 密钥 <ExternalLink aria-hidden="true" /></a>
    </div>
  </aside>;
}

function TextAreaField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return <label className="field"><span>{label}</span><textarea rows={3} value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /></label>;
}

function AnalysisPanel({ analysis }: { analysis: AnalysisResponse | null }) {
  if (!analysis) {
    return <div className="analysis-empty"><BrainCircuit aria-hidden="true" /><p>分析任务后，这里会解释策略选择和六维复杂度。</p></div>;
  }
  const strategy = analysis.routing.selected_strategy ?? analysis.routing.recommended_strategy;
  return <div className="analysis-content">
    <dl className="analysis-summary">
      <div><dt>任务类型</dt><dd>{TASK_LABELS[analysis.task.task_type] ?? analysis.task.task_type}</dd></div>
      <div><dt>推荐策略</dt><dd>{STRATEGY_LABELS[strategy] ?? strategy}</dd></div>
      <div><dt>目标模型</dt><dd>{AGENT_LABELS[analysis.task.target_agent]}</dd></div>
      <div className="score"><dt>复杂度</dt><dd>{analysis.complexity.total_score}<span>/18</span></dd></div>
    </dl>
    <div className="dimension-list">
      {DIMENSIONS.map(([key, label]) => {
        const value = analysis.complexity.dimensions[key];
        if (!value) return null;
        return <details key={key}>
          <summary><span>{label}</span><span className={`dimension-score score-${value.score}`}>{value.score} / 3</span></summary>
          <p>{value.reason}</p>
        </details>;
      })}
    </div>
    <div className="analysis-note"><strong>为什么这样安排</strong><p>{analysis.routing.reason}</p></div>
    {!!analysis.task.missing_information?.length && <div className="analysis-note warning"><strong>缺失信息</strong><ul>{analysis.task.missing_information.map((item) => <li key={item}>{item}</li>)}</ul></div>}
  </div>;
}

function ResultWorkspace({ run, selectedArtifact, content, previewMode, desktop, onSelect, onMode, onArchive }: {
  run: RunDetail;
  selectedArtifact: string;
  content: string;
  previewMode: "rendered" | "source";
  desktop: boolean;
  onSelect: (filename: string) => void;
  onMode: (mode: "rendered" | "source") => void;
  onArchive: () => void;
}) {
  const copyCurrent = async () => navigator.clipboard.writeText(content);
  const copyAll = async () => {
    const contents = await Promise.all(run.artifacts.filter((item) => item.filename.endsWith(".md")).map(async (item) => `# ${item.filename}\n\n${await api.artifact(run.id, item.filename)}`));
    await navigator.clipboard.writeText(contents.join("\n\n---\n\n"));
  };
  const openFolder = async () => window.pywebview?.api.open_run_folder(run.id);
  return <section className="surface result-surface" aria-labelledby="result-title">
    <div className="result-heading">
      <div><span className="quality"><Check aria-hidden="true" /> 质量检查 {run.quality_score}/100</span><h2 id="result-title">生成结果</h2></div>
      <div className="result-actions">
        <button className="button ghost" type="button" onClick={copyCurrent}><Copy aria-hidden="true" /> 复制当前</button>
        <button className="button ghost" type="button" onClick={copyAll}><Files aria-hidden="true" /> 复制全部</button>
        <a className="button ghost" href={`/api/v1/runs/${run.id}/download`} download><Download aria-hidden="true" /> 下载 ZIP</a>
        {desktop && <button className="button ghost" type="button" onClick={openFolder}><FolderOpen aria-hidden="true" /> 打开目录</button>}
        <button className="icon-button" type="button" aria-label="归档当前记录" onClick={onArchive}><Archive aria-hidden="true" /></button>
      </div>
    </div>
    <div className="artifact-workspace">
      <nav className="artifact-list" aria-label="生成文件">
        {run.artifacts.map((item) => <button key={item.filename} type="button" className={selectedArtifact === item.filename ? "is-selected" : ""} onClick={() => onSelect(item.filename)}><span>{item.filename.endsWith(".json") ? "{}" : "#"}</span>{item.filename}<small>{Math.max(1, Math.round(item.size / 1024))} KB</small></button>)}
      </nav>
      <div className="artifact-preview">
        <div className="preview-toolbar">
          <strong>{selectedArtifact || "选择文件"}</strong>
          <div role="group" aria-label="预览模式">
            <button type="button" aria-pressed={previewMode === "rendered"} onClick={() => onMode("rendered")}>预览</button>
            <button type="button" aria-pressed={previewMode === "source"} onClick={() => onMode("source")}>源码</button>
          </div>
        </div>
        {previewMode === "rendered" && selectedArtifact.endsWith(".md") ? <article className="markdown"><ReactMarkdown>{content}</ReactMarkdown></article> : <pre className="source"><code>{content}</code></pre>}
      </div>
    </div>
  </section>;
}

export default App;
