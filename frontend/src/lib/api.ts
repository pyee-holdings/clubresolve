// API client for ClubResolve backend

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
  }

  private headers(): HeadersInit {
    const h: HeadersInit = { "Content-Type": "application/json" };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...this.headers(), ...options.headers },
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || "Request failed");
    }
    return res.json();
  }

  // Auth
  async register(email: string, name: string, password: string) {
    return this.request<{ id: string; email: string; name: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, name, password }),
    });
  }

  async login(email: string, password: string) {
    return this.request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  async getMe() {
    return this.request<{ id: string; email: string; name: string }>("/api/auth/me");
  }

  // API Keys
  async saveApiKey(provider: string, apiKey: string, preferredModel?: string, modelTier = "strong") {
    return this.request("/api/keys", {
      method: "POST",
      body: JSON.stringify({
        provider,
        api_key: apiKey,
        preferred_model: preferredModel || null,
        model_tier: modelTier,
      }),
    });
  }

  async listApiKeys() {
    return this.request<Array<{ id: string; provider: string; preferred_model: string | null; model_tier: string; is_active: boolean }>>("/api/keys");
  }

  async deleteApiKey(provider: string) {
    return this.request(`/api/keys/${provider}`, { method: "DELETE" });
  }

  async validateApiKey(provider: string, apiKey: string) {
    return this.request<{ valid: boolean }>("/api/keys/validate", {
      method: "POST",
      body: JSON.stringify({ provider, api_key: apiKey }),
    });
  }

  // Cases
  async createCase(data: Record<string, unknown>) {
    return this.request<Record<string, unknown>>("/api/cases", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async listCases() {
    return this.request<Array<Record<string, unknown>>>("/api/cases");
  }

  async getCase(caseId: string) {
    return this.request<Record<string, unknown>>(`/api/cases/${caseId}`);
  }

  async updateCase(caseId: string, data: Record<string, unknown>) {
    return this.request(`/api/cases/${caseId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  async deleteCase(caseId: string) {
    return this.request(`/api/cases/${caseId}`, { method: "DELETE" });
  }

  async retryIntakeReview(caseId: string) {
    return this.request<Record<string, unknown>>(
      `/api/cases/${caseId}/review/retry`,
      { method: "POST" },
    );
  }

  // Case Questions (intake review)
  async listQuestions(caseId: string) {
    return this.request<Array<import("./types").CaseQuestion>>(
      `/api/cases/${caseId}/questions`,
    );
  }

  async answerQuestion(caseId: string, questionId: string, answer: string) {
    return this.request<import("./types").CaseQuestion>(
      `/api/cases/${caseId}/questions/${questionId}/answer`,
      { method: "POST", body: JSON.stringify({ answer }) },
    );
  }

  async dismissQuestion(caseId: string, questionId: string, reason?: string) {
    return this.request<import("./types").CaseQuestion>(
      `/api/cases/${caseId}/questions/${questionId}/dismiss`,
      { method: "POST", body: JSON.stringify({ reason: reason ?? null }) },
    );
  }

  // Evidence requests
  async listEvidenceRequests(caseId: string) {
    return this.request<Array<import("./types").EvidenceRequest>>(
      `/api/cases/${caseId}/evidence-requests`,
    );
  }

  async fulfillEvidenceRequestText(
    caseId: string,
    requestId: string,
    payload: {
      content: string;
      title?: string | null;
      source_reference?: string | null;
      event_date?: string | null;
    },
  ) {
    return this.request<import("./types").EvidenceRequest>(
      `/api/cases/${caseId}/evidence-requests/${requestId}/fulfill-text`,
      {
        method: "POST",
        body: JSON.stringify({
          content: payload.content,
          title: payload.title ?? null,
          source_reference: payload.source_reference ?? null,
          event_date: payload.event_date ?? null,
        }),
      },
    );
  }

  async fulfillEvidenceRequestFile(
    caseId: string,
    requestId: string,
    file: File,
    opts: {
      title?: string;
      source_reference?: string;
      event_date?: string;
    } = {},
  ) {
    const form = new FormData();
    form.append("file", file);
    if (opts.title) form.append("title", opts.title);
    if (opts.source_reference) form.append("source_reference", opts.source_reference);
    if (opts.event_date) form.append("event_date", opts.event_date);
    const res = await fetch(
      `${API_BASE}/api/cases/${caseId}/evidence-requests/${requestId}/fulfill-file`,
      {
        method: "POST",
        headers: this.token ? { Authorization: `Bearer ${this.token}` } : undefined,
        body: form,
      },
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || "Upload failed");
    }
    return (await res.json()) as import("./types").EvidenceRequest;
  }

  async markEvidenceRequestUnavailable(
    caseId: string,
    requestId: string,
    reason?: string,
  ) {
    return this.request<import("./types").EvidenceRequest>(
      `/api/cases/${caseId}/evidence-requests/${requestId}/mark-unavailable`,
      {
        method: "POST",
        body: JSON.stringify({ reason: reason ?? null }),
      },
    );
  }

  async dismissEvidenceRequest(caseId: string, requestId: string) {
    return this.request<import("./types").EvidenceRequest>(
      `/api/cases/${caseId}/evidence-requests/${requestId}/dismiss`,
      { method: "POST" },
    );
  }

  // Chat (SSE streaming)
  async sendMessage(caseId: string, message: string): Promise<ReadableStream<Uint8Array> | null> {
    const res = await fetch(`${API_BASE}/api/cases/${caseId}/chat`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ message }),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: "Chat request failed" }));
      throw new Error(error.detail || "Chat request failed");
    }
    return res.body;
  }

  async getMessages(caseId: string) {
    return this.request<Array<Record<string, unknown>>>(`/api/cases/${caseId}/messages`);
  }

  // Evidence
  async listEvidence(caseId: string) {
    return this.request<Array<Record<string, unknown>>>(`/api/cases/${caseId}/evidence`);
  }

  async addEvidence(caseId: string, data: Record<string, unknown>) {
    return this.request(`/api/cases/${caseId}/evidence`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // Timeline
  async getTimeline(caseId: string) {
    return this.request<Array<Record<string, unknown>>>(`/api/cases/${caseId}/timeline`);
  }

  // Drafts
  async listDrafts(caseId: string) {
    return this.request<Array<Record<string, unknown>>>(`/api/cases/${caseId}/drafts`);
  }

  // Wizard
  async generateActionPlan(intake: {
    province: string;
    sport: string;
    category: string;
    tried: string;
    desired_outcome: string;
    description: string;
    email: string;
  }) {
    return this.request<{
      summary: string;
      steps: Array<{
        title: string;
        description: string;
        citation: string;
        template: string;
        deadline: string;
      }>;
      escalation_timeline: Array<{
        if: string;
        then: string;
        deadline: string;
      }>;
      disclaimer: string;
    }>("/api/wizard/generate", {
      method: "POST",
      body: JSON.stringify(intake),
    });
  }
}

export const api = new ApiClient();
