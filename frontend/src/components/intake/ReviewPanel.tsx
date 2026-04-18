"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { CaseQuestion, QuestionPriority } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  CheckCircle2,
  HelpCircle,
  Loader2,
  RefreshCw,
  X,
  AlertTriangle,
  Sparkles,
} from "lucide-react";

// After this long in "reviewing" we assume the background task died and
// offer the user a manual retry.
const REVIEW_STUCK_THRESHOLD_MS = 90_000;

interface ReviewPanelProps {
  caseId: string;
  reviewStatus: "pending" | "reviewing" | "needs_input" | "complete";
  onAnyChange?: () => void;
}

const PRIORITY_STYLES: Record<
  QuestionPriority,
  { label: string; className: string; icon: React.ComponentType<{ className?: string }> }
> = {
  critical: {
    label: "Critical",
    className: "bg-red-50 text-red-700 border-red-200",
    icon: AlertTriangle,
  },
  important: {
    label: "Important",
    className: "bg-amber-50 text-amber-800 border-amber-200",
    icon: HelpCircle,
  },
  nice_to_have: {
    label: "Nice to have",
    className: "bg-slate-50 text-slate-700 border-slate-200",
    icon: HelpCircle,
  },
};

const CATEGORY_LABELS: Record<string, string> = {
  people: "People",
  timeline: "Timeline",
  evidence: "Evidence",
  policy: "Policy",
  outcome: "Outcome",
  general: "General",
};

function priorityOrder(q: CaseQuestion): number {
  return q.priority === "critical" ? 0 : q.priority === "important" ? 1 : 2;
}

export function ReviewPanel({ caseId, reviewStatus, onAnyChange }: ReviewPanelProps) {
  const [questions, setQuestions] = useState<CaseQuestion[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [reviewingSince, setReviewingSince] = useState<number | null>(null);
  const [isStuck, setIsStuck] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(
    async (opts?: { notifyParent?: boolean }) => {
      try {
        const rows = await api.listQuestions(caseId);
        setQuestions(rows);
        setError(null);
        if (opts?.notifyParent && rows.length > 0) {
          // Review finished producing questions while we were polling —
          // notify the parent so it reloads `review_status` and the
          // sidebar badge updates.
          onAnyChange?.();
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load questions");
      } finally {
        setLoading(false);
      }
    },
    [caseId, onAnyChange],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Track how long we've been in the `reviewing` state so we can surface
  // a retry button if the background task died.
  useEffect(() => {
    if (reviewStatus === "reviewing") {
      if (reviewingSince === null) setReviewingSince(Date.now());
    } else {
      setReviewingSince(null);
      setIsStuck(false);
    }
  }, [reviewStatus, reviewingSince]);

  useEffect(() => {
    if (reviewingSince === null) return;
    const timer = setTimeout(() => {
      setIsStuck(true);
    }, REVIEW_STUCK_THRESHOLD_MS);
    return () => clearTimeout(timer);
  }, [reviewingSince]);

  // While the backend is still producing questions (review_status=reviewing)
  // or the case has no API key yet (pending with empty list), poll every 3s.
  useEffect(() => {
    const shouldPoll =
      reviewStatus === "reviewing" ||
      (reviewStatus === "pending" && questions !== null && questions.length === 0);
    if (!shouldPoll) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = setInterval(
      () => refresh({ notifyParent: true }),
      3000,
    );
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [reviewStatus, questions, refresh]);

  const handleRetry = async () => {
    setRetrying(true);
    setError(null);
    try {
      await api.retryIntakeReview(caseId);
      setQuestions([]);
      setIsStuck(false);
      setReviewingSince(null);
      onAnyChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setRetrying(false);
    }
  };

  const handleAnswer = async (q: CaseQuestion) => {
    const answer = (drafts[q.id] ?? "").trim();
    if (!answer) return;
    setSubmittingId(q.id);
    try {
      const updated = await api.answerQuestion(caseId, q.id, answer);
      setQuestions((prev) =>
        prev ? prev.map((it) => (it.id === q.id ? updated : it)) : prev,
      );
      setDrafts((d) => {
        const n = { ...d };
        delete n[q.id];
        return n;
      });
      onAnyChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save answer");
    } finally {
      setSubmittingId(null);
    }
  };

  const handleDismiss = async (q: CaseQuestion) => {
    setSubmittingId(q.id);
    try {
      const updated = await api.dismissQuestion(caseId, q.id);
      setQuestions((prev) =>
        prev ? prev.map((it) => (it.id === q.id ? updated : it)) : prev,
      );
      onAnyChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to dismiss");
    } finally {
      setSubmittingId(null);
    }
  };

  // Empty/loading states
  if (loading && questions === null) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        <span className="text-sm text-muted-foreground">Loading review...</span>
      </div>
    );
  }

  if (reviewStatus === "reviewing") {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-8 text-center">
          <Sparkles className="h-6 w-6 text-primary" />
          <p className="text-sm font-medium">Reviewing your case...</p>
          <p className="text-xs text-muted-foreground">
            Reading your intake to find the most important gaps. Usually 5-15 seconds.
          </p>
          {isStuck && (
            <div className="mt-2 space-y-2">
              <p className="text-xs text-amber-700">
                Taking longer than expected. The review may have failed silently.
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={handleRetry}
                disabled={retrying}
              >
                {retrying ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <RefreshCw className="mr-1 h-3 w-3" />
                )}
                Retry review
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  if (reviewStatus === "pending" && (!questions || questions.length === 0)) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-6 text-center">
          <p className="text-sm text-muted-foreground">
            Intake review hasn&apos;t run yet. Add your LLM API key in Settings,
            then run the review.
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={handleRetry}
            disabled={retrying}
          >
            {retrying ? (
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            ) : (
              <RefreshCw className="mr-1 h-3 w-3" />
            )}
            Run review now
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!questions || questions.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-6 text-center">
          <CheckCircle2 className="h-6 w-6 text-emerald-500" />
          <p className="text-sm font-medium">No review questions</p>
          <p className="text-xs text-muted-foreground">
            Your intake looks complete. Head to the chat to plan your next steps.
          </p>
        </CardContent>
      </Card>
    );
  }

  const open = questions
    .filter((q) => q.status === "open")
    .sort((a, b) => priorityOrder(a) - priorityOrder(b));
  const resolved = questions.filter((q) => q.status !== "open");

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {open.length === 0 ? (
        <Card>
          <CardContent className="flex items-center gap-2 py-4">
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
            <p className="text-sm">
              All clarifying questions resolved. You&apos;re ready to plan.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">
              {open.length} question{open.length === 1 ? "" : "s"} to help me understand your case
            </h3>
          </div>

          {open.map((q) => {
            const p = PRIORITY_STYLES[q.priority];
            const PIcon = p.icon;
            const draft = drafts[q.id] ?? "";
            const isSubmitting = submittingId === q.id;
            return (
              <Card key={q.id}>
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className={`text-[10px] ${p.className}`}>
                      <PIcon className="mr-1 h-3 w-3" /> {p.label}
                    </Badge>
                    <Badge variant="secondary" className="text-[10px]">
                      {CATEGORY_LABELS[q.category] ?? q.category}
                    </Badge>
                  </div>
                  <CardTitle className="mt-2 text-sm leading-snug">
                    {q.question}
                  </CardTitle>
                  {q.context && (
                    <p className="text-xs text-muted-foreground">{q.context}</p>
                  )}
                </CardHeader>
                <CardContent className="space-y-2">
                  <Textarea
                    value={draft}
                    onChange={(e) =>
                      setDrafts((d) => ({ ...d, [q.id]: e.target.value }))
                    }
                    placeholder="Type your answer..."
                    rows={3}
                    disabled={isSubmitting}
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDismiss(q)}
                      disabled={isSubmitting}
                    >
                      <X className="mr-1 h-3 w-3" /> Not applicable
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleAnswer(q)}
                      disabled={isSubmitting || draft.trim().length === 0}
                    >
                      {isSubmitting ? (
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      ) : null}
                      Save answer
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {resolved.length > 0 && (
        <div className="space-y-2 pt-3">
          <h4 className="text-xs font-medium text-muted-foreground">
            Resolved ({resolved.length})
          </h4>
          {resolved.map((q) => (
            <Card key={q.id} className="bg-muted/30">
              <CardContent className="space-y-1 py-3 text-xs">
                <div className="flex items-center gap-2">
                  {q.status === "answered" ? (
                    <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                  ) : (
                    <X className="h-3 w-3 text-muted-foreground" />
                  )}
                  <p className="font-medium">{q.question}</p>
                </div>
                {q.answer && (
                  <p className="pl-5 text-muted-foreground">{q.answer}</p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
