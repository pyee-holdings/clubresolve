"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { useCaseStore, type AgentNotification } from "@/stores/caseStore";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Send, Loader2, Shield, Scale, Archive, PenTool, ChevronDown, ChevronUp, CheckCircle2 } from "lucide-react";

const AGENT_CONFIG: Record<string, { label: string; color: string; icon: typeof Shield }> = {
  navigator: { label: "Navigator", color: "bg-purple-100 text-purple-700", icon: Shield },
  counsel: { label: "Counsel", color: "bg-green-100 text-green-700", icon: Scale },
  vault: { label: "Vault", color: "bg-blue-100 text-blue-700", icon: Archive },
  drafts: { label: "Draft Studio", color: "bg-orange-100 text-orange-700", icon: PenTool },
};

const MAX_USER_MSG_LENGTH = 500;

function MessageBubble({ msg }: { msg: { id: string; role: string; agent_name: string | null; content: string } }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = msg.role === "user" && msg.content.length > MAX_USER_MSG_LENGTH;
  const displayContent = isLong && !expanded
    ? msg.content.slice(0, MAX_USER_MSG_LENGTH) + "..."
    : msg.content;

  return (
    <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-3 ${
          msg.role === "user"
            ? "bg-primary text-primary-foreground"
            : "bg-muted"
        }`}
      >
        {msg.role === "assistant" && msg.agent_name && (
          <div className="mb-1">
            <Badge
              className={`text-xs ${AGENT_CONFIG[msg.agent_name]?.color || "bg-gray-100"}`}
            >
              {AGENT_CONFIG[msg.agent_name]?.label || msg.agent_name}
            </Badge>
          </div>
        )}
        {msg.role === "assistant" ? (
          <div className="prose prose-sm max-w-none dark:prose-invert [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        ) : (
          <div className="whitespace-pre-wrap text-sm">{displayContent}</div>
        )}
        {isLong && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-1 flex items-center gap-1 text-xs opacity-70 hover:opacity-100"
          >
            {expanded ? (
              <><ChevronUp className="h-3 w-3" /> Show less</>
            ) : (
              <><ChevronDown className="h-3 w-3" /> Show full message ({msg.content.length} chars)</>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

const NOTIFICATION_CONFIG: Record<string, { icon: typeof Archive; bg: string; border: string }> = {
  evidence_added: { icon: Archive, bg: "bg-blue-50 dark:bg-blue-950", border: "border-blue-200 dark:border-blue-800" },
  draft_generated: { icon: PenTool, bg: "bg-orange-50 dark:bg-orange-950", border: "border-orange-200 dark:border-orange-800" },
  timeline_added: { icon: Scale, bg: "bg-green-50 dark:bg-green-950", border: "border-green-200 dark:border-green-800" },
};

function NotificationCard({ notification }: { notification: AgentNotification }) {
  const config = NOTIFICATION_CONFIG[notification.type] || NOTIFICATION_CONFIG.evidence_added;
  const Icon = config.icon;
  return (
    <div className={`flex items-center gap-2 rounded-lg border ${config.border} ${config.bg} px-4 py-2 text-sm`}>
      <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span>{notification.message}</span>
    </div>
  );
}

export function ChatPanel({ caseId }: { caseId: string }) {
  const { messages, notifications, isStreaming, currentAgent, sendMessage, loadMessages } = useCaseStore();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadMessages(caseId);
  }, [caseId, loadMessages]);

  useEffect(() => {
    // Auto-scroll to bottom when messages change
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || isStreaming) return;
    setInput("");
    await sendMessage(caseId, msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex min-h-0 h-full flex-col">
      {/* Messages — plain scrollable div */}
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="space-y-4">
          {messages.length === 0 && !isStreaming && (
            <div className="py-12 text-center">
              <Shield className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
              <p className="font-medium">Welcome to your case</p>
              <p className="text-sm text-muted-foreground">
                Tell the Navigator about your situation and it will help you plan next steps.
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}

          {/* Agent action notifications */}
          {notifications.map((n) => (
            <NotificationCard key={n.id} notification={n} />
          ))}

          {/* Scroll anchor */}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Streaming indicator */}
      {isStreaming && currentAgent && (
        <div className="flex items-center gap-2 border-t px-4 py-2 text-sm text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          {AGENT_CONFIG[currentAgent]?.label || "Agent"} is working...
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 border-t p-4">
        <div className="flex gap-2">
          <Textarea
            placeholder="Describe your situation or ask a question..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            className="resize-none max-h-32 overflow-y-auto"
            disabled={isStreaming}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            className="self-end"
          >
            {isStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
