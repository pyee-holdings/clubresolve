import { create } from "zustand";
import { api } from "@/lib/api";
import type { Case, ChatMessage } from "@/lib/types";

export interface AgentNotification {
  id: string;
  type: "evidence_added" | "draft_generated" | "timeline_added";
  message: string;
  count?: number;
  items?: unknown[];
}

interface CaseState {
  cases: Case[];
  activeCase: Case | null;
  messages: ChatMessage[];
  notifications: AgentNotification[];
  isStreaming: boolean;
  currentAgent: string | null;

  loadCases: () => Promise<void>;
  loadCase: (id: string) => Promise<void>;
  loadMessages: (caseId: string) => Promise<void>;
  sendMessage: (caseId: string, message: string) => Promise<void>;
  createCase: (data: Record<string, unknown>) => Promise<Case>;
  deleteCase: (caseId: string) => Promise<void>;
}

export const useCaseStore = create<CaseState>((set, get) => ({
  cases: [],
  activeCase: null,
  messages: [],
  notifications: [],
  isStreaming: false,
  currentAgent: null,

  loadCases: async () => {
    const cases = (await api.listCases()) as unknown as Case[];
    set({ cases });
  },

  loadCase: async (id) => {
    const activeCase = (await api.getCase(id)) as unknown as Case;
    set({ activeCase });
  },

  loadMessages: async (caseId) => {
    const messages = (await api.getMessages(caseId)) as unknown as ChatMessage[];
    set({ messages });
  },

  createCase: async (data) => {
    const newCase = (await api.createCase(data)) as unknown as Case;
    set((s) => ({ cases: [newCase, ...s.cases] }));
    return newCase;
  },

  deleteCase: async (caseId) => {
    await api.deleteCase(caseId);
    set((s) => ({ cases: s.cases.filter((c) => c.id !== caseId) }));
  },

  sendMessage: async (caseId, message) => {
    // Add user message optimistically
    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      case_id: caseId,
      role: "user",
      agent_name: null,
      content: message,
      metadata_json: null,
      created_at: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, userMsg], isStreaming: true }));

    try {
      const stream = await api.sendMessage(caseId, message);
      if (!stream) return;

      const reader = stream.getReader();
      const decoder = new TextDecoder();
      let assistantContent = "";
      let agentName = "navigator";

      // Clear notifications from previous message
      set({ notifications: [] });

      // Add placeholder for assistant message
      const assistantMsg: ChatMessage = {
        id: `temp-assistant-${Date.now()}`,
        case_id: caseId,
        role: "assistant",
        agent_name: agentName,
        content: "",
        metadata_json: null,
        created_at: new Date().toISOString(),
      };
      set((s) => ({ messages: [...s.messages, assistantMsg] }));

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "agent_start") {
              agentName = event.agent || "navigator";
              set({ currentAgent: agentName });
            } else if (event.type === "token") {
              assistantContent += event.content || "";
              set((s) => ({
                messages: s.messages.map((m) =>
                  m.id === assistantMsg.id
                    ? { ...m, content: assistantContent, agent_name: event.agent || agentName }
                    : m
                ),
              }));
            } else if (event.type === "evidence_added") {
              const items = event.items || [];
              const count = Array.isArray(items) ? items.length : 0;
              if (count > 0) {
                set((s) => ({
                  notifications: [
                    ...s.notifications,
                    {
                      id: `notif-evidence-${Date.now()}`,
                      type: "evidence_added" as const,
                      message: `Vault added ${count} evidence item${count !== 1 ? "s" : ""}`,
                      count,
                      items,
                    },
                  ],
                }));
              }
            } else if (event.type === "draft_generated") {
              const drafts = Array.isArray(event.draft) ? event.draft : event.draft ? [event.draft] : [];
              for (const d of drafts) {
                const title = (d as Record<string, unknown>)?.title || "Draft Communication";
                set((s) => ({
                  notifications: [
                    ...s.notifications,
                    {
                      id: `notif-draft-${Date.now()}-${Math.random()}`,
                      type: "draft_generated" as const,
                      message: `Draft Studio created: ${title}`,
                    },
                  ],
                }));
              }
            } else if (event.type === "agent_end") {
              set({ currentAgent: null });
            }
          } catch {
            // Skip malformed events
          }
        }
      }
    } catch (err) {
      // Show error as an assistant message
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        case_id: caseId,
        role: "assistant",
        agent_name: "navigator",
        content: `**Error:** ${err instanceof Error ? err.message : "Something went wrong. Please try again."}`,
        metadata_json: null,
        created_at: new Date().toISOString(),
      };
      set((s) => ({ messages: [...s.messages, errorMsg] }));
    } finally {
      set({ isStreaming: false, currentAgent: null });
    }
  },
}));
