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
}

export const api = new ApiClient();
