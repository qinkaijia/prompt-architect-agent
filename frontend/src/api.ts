import type {
  AnalysisResponse,
  ApiErrorDetail,
  GenerationRequest,
  MetaResponse,
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
};
