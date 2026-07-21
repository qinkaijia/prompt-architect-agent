export type TargetAgent = "codex" | "claude_code" | "chat_model" | "image_model";
export type Language = "zh-CN" | "en";

export interface GenerationRequest {
  raw_request: string;
  target_agent?: TargetAgent;
  deliverables: string[];
  known_context: string[];
  available_files: string[];
  constraints: string[];
  forbidden_actions: string[];
  tools: string[];
  acceptance_criteria: string[];
  language: Language;
  allow_staged: boolean;
}

export interface DimensionScore {
  score: number;
  reason: string;
  signals: string[];
}

export interface AnalysisResponse {
  task: Record<string, unknown> & {
    normalized_goal: string;
    task_type: string;
    target_agent: TargetAgent;
    missing_information: string[];
    risk_level: string;
  };
  complexity: {
    dimensions: Record<string, DimensionScore>;
    total_score: number;
    recommended_strategy: string;
    reason: string;
  };
  routing: {
    recommended_strategy: string;
    selected_strategy: string | null;
    blocked: boolean;
    reason: string;
    warnings: string[];
  };
  blockers: string[];
}

export interface ArtifactMetadata {
  filename: string;
  media_type: string;
  size: number;
  download_url: string;
}

export interface RunSummary {
  id: string;
  created_at: string;
  title: string;
  normalized_goal: string;
  target_agent: TargetAgent;
  task_type: string;
  strategy: string;
  complexity_score: number;
  quality_score: number;
  status: "ready" | "archived";
}

export interface RunDetail extends RunSummary {
  sanitized_request: string;
  output_dir: string;
  task: Record<string, unknown>;
  complexity: AnalysisResponse["complexity"];
  review: {
    passed: boolean;
    score: number;
    issues: Array<{ code: string; severity: string; message: string; artifact?: string }>;
    suggestions: string[];
    repair_attempted: boolean;
  };
  artifacts: ArtifactMetadata[];
}

export interface RunListResponse {
  items: RunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface MetaResponse {
  version: string;
  desktop: boolean;
  target_agents: TargetAgent[];
  languages: Language[];
  task_types: string[];
  strategies: string[];
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  questions: string[];
  context: Record<string, unknown>;
}

export interface ModelInfo {
  id: string;
  owned_by: string;
}

export interface ProviderStatus {
  provider: "deepseek";
  configured: boolean;
  source: "environment" | "credential_store" | "none";
  key_hint: string | null;
  connected: boolean;
  default_model: string;
  models: ModelInfo[];
  message: string;
}

export interface ContextGrant {
  id: string;
  files: Array<{ name: string; readable: boolean }>;
}

export interface AgentSession {
  id: string;
  status: "pending" | "clarifying" | "generating" | "reviewing" | "repairing" | "completed" | "failed" | "cancelled";
  model_id: string;
  questions: string[];
  clarification_round: number;
  run_id: string | null;
  last_error: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  run: RunDetail | null;
}

export interface AgentEvent {
  event: string;
  data: Record<string, unknown>;
}

declare global {
  interface Window {
    pywebview?: {
      api: {
        choose_files: () => Promise<string[]>;
        choose_directory: () => Promise<string | null>;
        open_run_folder: (runId: string) => Promise<boolean>;
      };
    };
  }
}
