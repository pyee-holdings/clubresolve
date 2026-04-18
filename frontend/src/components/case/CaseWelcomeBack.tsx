"use client";

/**
 * Phase D "Welcome back" card.
 *
 * Renders at the top of the case detail page. Three jobs:
 *   1. Orient the user ("last visit 3 days ago" / "new case")
 *   2. Surface what's new since last visit (plan updated, new agent
 *      questions, new evidence requests)
 *   3. Point at the single next best action so the user knows where to go
 *
 * Fetches questions + evidence requests itself on mount (one-shot) so it
 * doesn't require the parent to hoist state. Dismissible.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  Case,
  CaseQuestion,
  EvidenceRequest,
  PlanStep,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ArrowRight,
  CheckCircle2,
  HelpCircle,
  Loader2,
  Paperclip,
  Sparkles,
  Target,
  X,
} from "lucide-react";

interface Props {
  activeCase: Case;
  previousVisitedAt: string | null;
  onJumpToReview: () => void;
  onJumpToStrategy: () => void;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return d.toLocaleDateString();
}

function isAfter(a: string | null | undefined, b: string | null): boolean {
  if (!a) return false;
  if (!b) return true; // never visited before → everything is "new"
  return new Date(a).getTime() > new Date(b).getTime();
}

/** Decide the single next action the user should take. Rule-based. */
function chooseNextAction(
  activeCase: Case,
  questions: CaseQuestion[],
  evidenceRequests: EvidenceRequest[],
): { label: string; detail: string | null; target: "review" | "strategy" } | null {
  const openCriticalQ = questions.find(
    (q) => q.status === "open" && q.priority === "critical",
  );
  if (openCriticalQ) {
    return {
      label: "Answer a critical question",
      detail: openCriticalQ.question,
      target: "review",
    };
  }
  const openCriticalE = evidenceRequests.find(
    (r) => r.status === "open" && r.priority === "critical",
  );
  if (openCriticalE) {
    return {
      label: "Provide critical evidence",
      detail: openCriticalE.title,
      target: "review",
    };
  }
  const openQ = questions.filter((q) => q.status === "open");
  const openE = evidenceRequests.filter((r) => r.status === "open");
  if (openQ.length + openE.length > 0) {
    const qPart = openQ.length
      ? `${openQ.length} question${openQ.length === 1 ? "" : "s"}`
      : null;
    const ePart = openE.length
      ? `${openE.length} evidence item${openE.length === 1 ? "" : "s"}`
      : null;
    return {
      label: "Resolve what the agent is asking",
      detail: [qPart, ePart].filter(Boolean).join(" + "),
      target: "review",
    };
  }
  if (activeCase.next_steps && activeCase.next_steps.length > 0) {
    const first: PlanStep = activeCase.next_steps[0];
    return {
      label: "Take the next step in the plan",
      detail: first.step,
      target: "strategy",
    };
  }
  if (activeCase.plan_status === "error") {
    return {
      label: "Retry the plan",
      detail: "The last planning attempt failed. Run it again.",
      target: "strategy",
    };
  }
  if (activeCase.plan_status === "idle") {
    return {
      label: "Run the strategic plan",
      detail: "No plan yet. Generate one from the current state of your case.",
      target: "strategy",
    };
  }
  return null;
}

export function CaseWelcomeBack({
  activeCase,
  previousVisitedAt,
  onJumpToReview,
  onJumpToStrategy,
}: Props) {
  const [questions, setQuestions] = useState<CaseQuestion[] | null>(null);
  const [evidenceRequests, setEvidenceRequests] = useState<
    EvidenceRequest[] | null
  >(null);
  const [dismissed, setDismissed] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [q, e] = await Promise.all([
        api.listQuestions(activeCase.id),
        api.listEvidenceRequests(activeCase.id),
      ]);
      setQuestions(q);
      setEvidenceRequests(e);
    } catch {
      // If the fetch fails we just won't show counts. Non-critical.
      setQuestions([]);
      setEvidenceRequests([]);
    }
  }, [activeCase.id]);

  // Refresh when the case's updated_at changes — this catches any Review
  // tab action (answering a question, fulfilling evidence) that reloaded
  // the case in the parent. Without this, the "next action" would keep
  // pointing at a question the user already answered.
  useEffect(() => {
    loadData();
  }, [loadData, activeCase.updated_at]);

  const whatsNew = useMemo(() => {
    if (!questions || !evidenceRequests) return null;
    // On the very first visit `previousVisitedAt` is null — we don't want
    // to claim everything is "new since your last visit" because there
    // was no prior visit. The first-visit branch below handles that case.
    if (previousVisitedAt === null) {
      return { newQuestions: [], newEvidence: [], planFresh: false };
    }
    const newQuestions = questions.filter((q) =>
      isAfter(q.created_at, previousVisitedAt),
    );
    const newEvidence = evidenceRequests.filter((r) =>
      isAfter(r.created_at, previousVisitedAt),
    );
    const planFresh = isAfter(activeCase.plan_generated_at, previousVisitedAt);
    return { newQuestions, newEvidence, planFresh };
  }, [
    questions,
    evidenceRequests,
    previousVisitedAt,
    activeCase.plan_generated_at,
  ]);

  const nextAction = useMemo(() => {
    if (!questions || !evidenceRequests) return null;
    return chooseNextAction(activeCase, questions, evidenceRequests);
  }, [activeCase, questions, evidenceRequests]);

  if (dismissed) return null;

  // Before the data loads, render a compact placeholder so the layout doesn't
  // jump when it arrives.
  if (questions === null || evidenceRequests === null) {
    return (
      <Card className="mb-3 border-primary/30 bg-primary/5">
        <CardContent className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Getting you up to speed...
        </CardContent>
      </Card>
    );
  }

  const isFirstVisit = previousVisitedAt === null;
  const hasNew =
    whatsNew &&
    (whatsNew.newQuestions.length > 0 ||
      whatsNew.newEvidence.length > 0 ||
      whatsNew.planFresh);

  // If it's a repeat visit with nothing new AND no pending action, collapse.
  if (!isFirstVisit && !hasNew && !nextAction) {
    return null;
  }

  return (
    <Card className="mb-3 border-primary/30 bg-primary/5">
      <CardContent className="space-y-3 py-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="flex items-center gap-1 text-sm font-semibold">
              <Sparkles className="h-4 w-4 text-primary" />
              {isFirstVisit
                ? "Welcome to your case"
                : `Welcome back — last visit ${formatRelative(previousVisitedAt)}`}
            </h2>
          </div>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 shrink-0"
            onClick={() => setDismissed(true)}
            aria-label="Dismiss"
          >
            <X className="h-3 w-3" />
          </Button>
        </div>

        {hasNew && whatsNew && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">
              Since your last visit:
            </p>
            <ul className="space-y-1 text-sm">
              {whatsNew.planFresh && (
                <li className="flex items-start gap-2">
                  <Target className="mt-0.5 h-3.5 w-3.5 text-primary shrink-0" />
                  <span>
                    <button
                      onClick={onJumpToStrategy}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      New action plan ready
                    </button>
                    {activeCase.next_steps && activeCase.next_steps.length > 0 && (
                      <span className="text-muted-foreground">
                        {" "}
                        ({activeCase.next_steps.length} step
                        {activeCase.next_steps.length === 1 ? "" : "s"})
                      </span>
                    )}
                  </span>
                </li>
              )}
              {whatsNew.newQuestions.length > 0 && (
                <li className="flex items-start gap-2">
                  <HelpCircle className="mt-0.5 h-3.5 w-3.5 text-amber-600 shrink-0" />
                  <span>
                    <button
                      onClick={onJumpToReview}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {whatsNew.newQuestions.length} new question
                      {whatsNew.newQuestions.length === 1 ? "" : "s"}
                    </button>
                    <span className="text-muted-foreground"> from the agent</span>
                  </span>
                </li>
              )}
              {whatsNew.newEvidence.length > 0 && (
                <li className="flex items-start gap-2">
                  <Paperclip className="mt-0.5 h-3.5 w-3.5 text-amber-600 shrink-0" />
                  <span>
                    <button
                      onClick={onJumpToReview}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {whatsNew.newEvidence.length} new evidence request
                      {whatsNew.newEvidence.length === 1 ? "" : "s"}
                    </button>
                  </span>
                </li>
              )}
            </ul>
          </div>
        )}

        {isFirstVisit && !hasNew && (
          <p className="text-sm text-muted-foreground">
            We&apos;ll keep track of everything here. The agent will generate
            clarifying questions and a plan based on what you told us at
            intake.
          </p>
        )}

        {nextAction && (
          <div className="flex items-start justify-between gap-2 rounded-md border border-primary/20 bg-white p-3">
            <div className="min-w-0">
              <div className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
                <CheckCircle2 className="h-3 w-3" /> Suggested next action
              </div>
              <p className="mt-0.5 text-sm font-medium">{nextAction.label}</p>
              {nextAction.detail && (
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {nextAction.detail}
                </p>
              )}
            </div>
            <Button
              size="sm"
              onClick={
                nextAction.target === "review" ? onJumpToReview : onJumpToStrategy
              }
              className="shrink-0"
            >
              Go <ArrowRight className="ml-1 h-3 w-3" />
            </Button>
          </div>
        )}

        {/* Quick stat line — always show counts for orientation */}
        <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
          <Badge variant="outline" className="font-normal">
            {questions.filter((q) => q.status === "open").length} open question
            {questions.filter((q) => q.status === "open").length === 1 ? "" : "s"}
          </Badge>
          <Badge variant="outline" className="font-normal">
            {evidenceRequests.filter((r) => r.status === "open").length} open
            evidence request
            {evidenceRequests.filter((r) => r.status === "open").length === 1
              ? ""
              : "s"}
          </Badge>
          <Badge variant="outline" className="font-normal">
            {activeCase.plan_status === "ready"
              ? `plan ${formatRelative(activeCase.plan_generated_at)}`
              : activeCase.plan_status === "planning"
              ? "plan in progress..."
              : "no plan yet"}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}
