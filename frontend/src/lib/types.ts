// API types matching backend schemas

export interface User {
  id: string;
  email: string;
  name: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface APIKeyConfig {
  id: string;
  provider: string;
  preferred_model: string | null;
  model_tier: string;
  is_active: boolean;
}

export interface Case {
  id: string;
  title: string;
  category: string | null;
  club_name: string | null;
  sport: string | null;
  description: string | null;
  desired_outcome: string | null;
  urgency: string;
  risk_flags: string[] | null;
  people_involved: { name: string; role: string }[] | null;
  prior_attempts: string | null;
  status: string;
  escalation_level: number;
  strategy_plan: string | null;
  legal_summary: string | null;
  next_steps: { step: string; due: string; priority: string }[] | null;
  missing_info: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  case_id: string;
  role: "user" | "assistant";
  agent_name: string | null;
  content: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface EvidenceItem {
  id: string;
  case_id: string;
  title: string;
  description: string | null;
  evidence_type: string;
  source_reference: string | null;
  file_path: string | null;
  content: string | null;
  extracted_snippets: Record<string, unknown>[] | null;
  tags: string[] | null;
  collected_by: string;
  event_date: string | null;
  unanswered_questions: string[] | null;
  created_at: string;
}

export interface TimelineEvent {
  id: string;
  case_id: string;
  event_date: string;
  description: string;
  evidence_ids: string[] | null;
  source: string | null;
  event_type: string | null;
  created_at: string;
}

export interface Draft {
  id: string;
  case_id: string;
  draft_type: string;
  title: string;
  content: string;
  recipient: string | null;
  tone: string;
  status: string;
  generated_by: string;
  created_at: string;
  updated_at: string;
}

// SSE event types from chat endpoint
export type SSEEventType =
  | "agent_start"
  | "token"
  | "tool_call"
  | "evidence_added"
  | "draft_generated"
  | "next_steps"
  | "agent_end"
  | "error";

export interface SSEEvent {
  type: SSEEventType;
  content?: string;
  agent?: string;
  message?: string;
  items?: unknown[];
  draft?: unknown;
  steps?: unknown[];
}
