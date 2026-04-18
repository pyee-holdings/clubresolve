"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Case, PlanStep } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertTriangle,
  Loader2,
  RefreshCw,
  Sparkles,
  Target,
} from "lucide-react";

// Auto-stop polling after this many milliseconds to avoid hammering the server
// if the planner got stuck.
const POLL_TIMEOUT_MS = 180_000;
const POLL_INTERVAL_MS = 3_000;

interface Props {
  activeCase: Case;
  onCaseChange: () => void;
}

const PRIORITY_STYLES: Record<
  NonNullable<PlanStep["priority"]>,
  { label: string; className: string }
> = {
  critical: {
    label: "Critical",
    className: "bg-red-50 text-red-700 border-red-200",
  },
  important: {
    label: "Important",
    className: "bg-amber-50 text-amber-800 border-amber-200",
  },
  nice_to_have: {
    label: "Nice to have",
    className: "bg-slate-50 text-slate-700 border-slate-200",
  },
};

const ESCALATION_LABELS = [
  "Internal (coach / staff / board)",
  "Governing body (provincial organization)",
  "Formal complaint (registrar / safe sport)",
  "Legal",
];

function formatRelative(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

// After this long in "planning" we assume the background task died and
// surface a retry button.
const PLAN_STUCK_THRESHOLD_MS = 90_000;

export function StrategyPanel({ activeCase, onCaseChange }: Props) {
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isStuck, setIsStuck] = useState(false);
  const pollStartedAtRef = useRef<number | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Capture the latest callback in a ref so the polling effect doesn't
  // re-register every parent render when `onCaseChange` gets a new identity.
  const onCaseChangeRef = useRef(onCaseChange);
  useEffect(() => {
    onCaseChangeRef.current = onCaseChange;
  }, [onCaseChange]);

  const isPlanning = activeCase.plan_status === "planning";

  const clearPoll = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    pollStartedAtRef.current = null;
  }, []);

  // Poll for updates while the planner is running. Depends only on
  // `isPlanning` + `clearPoll` — the callback lives in a ref so parent
  // re-renders don't churn the interval.
  useEffect(() => {
    if (!isPlanning) {
      clearPoll();
      setIsStuck(false);
      return;
    }
    if (pollIntervalRef.current) return;
    pollStartedAtRef.current = Date.now();
    pollIntervalRef.current = setInterval(() => {
      if (
        pollStartedAtRef.current &&
        Date.now() - pollStartedAtRef.current > POLL_TIMEOUT_MS
      ) {
        clearPoll();
        setIsStuck(true);
        return;
      }
      onCaseChangeRef.current();
    }, POLL_INTERVAL_MS);
    return () => clearPoll();
  }, [isPlanning, clearPoll]);

  // Mark the panel "stuck" after the threshold so the user can retry.
  useEffect(() => {
    if (!isPlanning) return;
    const timer = setTimeout(() => setIsStuck(true), PLAN_STUCK_THRESHOLD_MS);
    return () => clearTimeout(timer);
  }, [isPlanning]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setError(null);
    setIsStuck(false);
    try {
      await api.regeneratePlan(activeCase.id);
      onCaseChangeRef.current();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start plan");
    } finally {
      setRegenerating(false);
    }
  };

  const hasPlan = !!activeCase.strategy_plan || (activeCase.next_steps?.length ?? 0) > 0;
  const lastUpdated = formatRelative(activeCase.plan_generated_at);

  return (
    <div className="space-y-4">
      {/* Risk flags */}
      {activeCase.risk_flags && activeCase.risk_flags.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-1 text-sm">
              <AlertTriangle className="h-4 w-4 text-red-500" /> Risk Flags
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-1">
              {activeCase.risk_flags.map((flag) => (
                <Badge key={flag} variant="destructive" className="text-xs">
                  {flag.replace(/_/g, " ")}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Plan header + regenerate */}
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex items-center gap-1 text-sm font-semibold">
            <Target className="h-4 w-4" /> Strategic plan
          </h3>
          {lastUpdated && (
            <p className="text-xs text-muted-foreground">
              Updated {lastUpdated}
            </p>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={handleRegenerate}
          // Allow retry when the planner appears stuck, even though
          // plan_status is still "planning".
          disabled={regenerating || (isPlanning && !isStuck)}
        >
          {regenerating || (isPlanning && !isStuck) ? (
            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="mr-1 h-3 w-3" />
          )}
          {isStuck ? "Retry plan" : hasPlan ? "Update plan" : "Run plan"}
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Planning in progress */}
      {isPlanning && !hasPlan && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-8 text-center">
            <Sparkles className="h-6 w-6 text-primary" />
            <p className="text-sm font-medium">Thinking through the plan...</p>
            <p className="text-xs text-muted-foreground">
              Reading your answered questions and the evidence you&apos;ve
              provided. Usually 10-20 seconds.
            </p>
            {isStuck && (
              <div className="mt-2 space-y-2">
                <p className="text-xs text-amber-700">
                  Taking longer than expected. The planner may have failed silently.
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleRegenerate}
                  disabled={regenerating}
                >
                  {regenerating ? (
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-1 h-3 w-3" />
                  )}
                  Retry plan
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeCase.plan_status === "error" && !isPlanning && (
        <Card>
          <CardContent className="py-4 text-sm text-muted-foreground">
            The last planning attempt failed. Use the button above to retry.
          </CardContent>
        </Card>
      )}

      {/* Plan narrative */}
      {activeCase.strategy_plan && (
        <Card>
          <CardContent className="py-4 text-sm leading-relaxed whitespace-pre-wrap">
            {activeCase.strategy_plan}
          </CardContent>
        </Card>
      )}

      {/* Next steps */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Next steps</CardTitle>
        </CardHeader>
        <CardContent>
          {activeCase.next_steps && activeCase.next_steps.length > 0 ? (
            <ol className="space-y-3 text-sm">
              {activeCase.next_steps.map((step, i) => {
                const prio = step.priority ?? "important";
                const p = PRIORITY_STYLES[prio];
                return (
                  <li key={i} className="flex gap-2">
                    <span className="font-medium text-primary">{i + 1}.</span>
                    <div className="min-w-0 flex-1 space-y-1">
                      <p>{step.step}</p>
                      {step.why && (
                        <p className="text-xs text-muted-foreground">
                          {step.why}
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-1 pt-0.5">
                        <Badge
                          variant="outline"
                          className={`text-[10px] ${p.className}`}
                        >
                          {p.label}
                        </Badge>
                        {step.due && (
                          <Badge variant="secondary" className="text-[10px]">
                            {step.due}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : hasPlan ? (
            <p className="text-sm text-muted-foreground">
              No specific steps in this plan yet.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              {activeCase.review_status === "needs_input"
                ? "Answer the Review questions above so the planner has enough to work with."
                : "Run the plan once you're ready."}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Missing info */}
      {activeCase.missing_info && activeCase.missing_info.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">What would strengthen the plan</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm text-muted-foreground">
              {activeCase.missing_info.map((info, i) => (
                <li key={i}>- {info}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Escalation level */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Escalation level</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2">
            {[0, 1, 2, 3].map((level) => (
              <div
                key={level}
                className={`h-2 flex-1 rounded-full ${
                  level <= activeCase.escalation_level
                    ? "bg-orange-400"
                    : "bg-gray-200"
                }`}
              />
            ))}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {ESCALATION_LABELS[activeCase.escalation_level] ?? "Unknown"}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
