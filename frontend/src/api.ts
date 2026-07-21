import type {
  AnalysisResponse,
  AgentEvent,
  AgentSession,
  ApiErrorDetail,
  ContextGrant,
  GenerationRequest,
  MetaResponse,
  ModelInfo,
  ProviderStatus,
  RunDetail,
  RunListResponse,
} from "./types";

export class ApiClientError extends Error {
  constructor(
    public status: number,
    public detail: ApiErrorDetail,
  ) {
    super(detail.message);
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = (await response.json()) as { detail?: ApiErrorDetail };
    throw new ApiClientError(response.status, payload.detail ?? {
      code: "request_failed",
      message: "请求失败，请稍后重试。",
      questions: [],
      context: {},
    });
  }
  return response.json() as Promise<T>;
}

async function parseEventStream(response: Response, onEvent: (event: AgentEvent) => void) {
  if (!response.ok) {
    const payload = (await response.json()) as { detail?: ApiErrorDetail };
    throw new ApiClientError(response.status, payload.detail ?? { code: "request_failed", message: "请求失败。", questions: [], context: {} });
  }
  if (!response.body) throw new Error("当前环境不支持流式响应。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let event = "message";
      let data = "{}";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        if (line.startsWith("data: ")) data = line.slice(6);
      }
      onEvent({ event, data: JSON.parse(data) as Record<string, unknown> });
    }
    if (done) break;
  }
}

export const api = {
  meta: () => requestJson<MetaResponse>("/api/v1/meta"),
  analyze: (payload: GenerationRequest) =>
    requestJson<AnalysisResponse>("/api/v1/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  generate: (payload: GenerationRequest) =>
    requestJson<RunDetail>("/api/v1/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  history: (query = "", status = "ready") =>
    requestJson<RunListResponse>(
      `/api/v1/runs?query=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`,
    ),
  run: (id: string) => requestJson<RunDetail>(`/api/v1/runs/${id}`),
  artifact: async (runId: string, filename: string) => {
    const response = await fetch(
      `/api/v1/runs/${runId}/artifacts/${encodeURIComponent(filename)}`,
    );
    if (!response.ok) throw new Error("无法读取生成文件");
    return response.text();
  },
  archive: (id: string) =>
    requestJson<RunDetail>(`/api/v1/runs/${id}/archive`, { method: "POST" }),
  importHistory: (path: string) =>
    requestJson<{ imported: number }>("/api/v1/history/import", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  provider: () => requestJson<ProviderStatus>("/api/v1/providers/deepseek"),
  saveCredential: (apiKey: string) =>
    requestJson<ProviderStatus>("/api/v1/providers/deepseek/credential", {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    }),
  deleteCredential: () =>
    requestJson<ProviderStatus>("/api/v1/providers/deepseek/credential", { method: "DELETE" }),
  testProvider: () =>
    requestJson<ProviderStatus>("/api/v1/providers/deepseek/test", { method: "POST" }),
  models: () => requestJson<{ items: ModelInfo[] }>("/api/v1/providers/deepseek/models"),
  setDefaultModel: (modelId: string) =>
    requestJson<{ model_id: string }>("/api/v1/settings/default-model", {
      method: "PUT",
      body: JSON.stringify({ model_id: modelId }),
    }),
  grantDesktop: (paths: string[]) =>
    requestJson<ContextGrant>("/api/v1/context/grants", {
      method: "POST",
      body: JSON.stringify({ paths }),
    }),
  uploadContext: async (files: File[]) => {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    const response = await fetch("/api/v1/context/uploads", { method: "POST", body });
    if (!response.ok) {
      const payload = (await response.json()) as { detail?: ApiErrorDetail };
      throw new ApiClientError(response.status, payload.detail ?? { code: "upload_failed", message: "文件上传失败。", questions: [], context: {} });
    }
    return response.json() as Promise<ContextGrant>;
  },
  createAgentSession: (payload: GenerationRequest & { model_id: string; offline_rules: boolean; context_grants: string[] }) =>
    requestJson<AgentSession>("/api/v1/agent/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  agentTurn: async (sessionId: string, answers: string[], onEvent: (event: AgentEvent) => void) => {
    const response = await fetch(`/api/v1/agent/sessions/${sessionId}/turns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    });
    await parseEventStream(response, onEvent);
  },
  cancelAgent: (sessionId: string) =>
    requestJson<{ cancelled: boolean }>(`/api/v1/agent/sessions/${sessionId}/cancel`, { method: "POST" }),
};
