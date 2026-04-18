"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { useCaseStore } from "@/stores/caseStore";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { CaseWelcomeBack } from "@/components/case/CaseWelcomeBack";
import { ReviewPanel } from "@/components/intake/ReviewPanel";
import { EvidenceRequestPanel } from "@/components/intake/EvidenceRequestPanel";
import { StrategyPanel } from "@/components/strategy/StrategyPanel";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, Archive, PenTool } from "lucide-react";

export default function CaseDetailPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params.id as string;
  const { user, isLoading, loadFromStorage } = useAuthStore();
  const { activeCase, loadCase } = useCaseStore();
  const [sidebarTab, setSidebarTab] = useState<string | null>(null);
  // Captured from the /visit endpoint — the previous last_visited_at
  // BEFORE this visit. Null on first visit ever.
  const [previousVisitedAt, setPreviousVisitedAt] = useState<string | null | undefined>(
    undefined, // undefined = not yet captured, null = never visited before
  );

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/auth/login");
    } else if (user && caseId) {
      loadCase(caseId);
    }
  }, [user, isLoading, caseId, router, loadCase]);

  // Record this visit exactly once per caseId. Next.js App Router reuses
  // the [id] route component across dynamic-segment changes, so we must
  // reset previousVisitedAt when caseId changes rather than relying on
  // remount.
  useEffect(() => {
    if (!user || !caseId) return;
    let cancelled = false;
    setPreviousVisitedAt(undefined);
    api
      .markCaseVisited(caseId)
      .then((r) => {
        if (!cancelled) setPreviousVisitedAt(r.previous_visited_at);
      })
      .catch(() => {
        // If the visit call fails, fall back to "first visit" treatment so
        // the welcome card still renders useful content.
        if (!cancelled) setPreviousVisitedAt(null);
      });
    return () => {
      cancelled = true;
    };
  }, [user, caseId]);

  // Auto-select the Review tab when the agent still needs answers.
  // Only runs when the user hasn't already switched tabs.
  useEffect(() => {
    if (sidebarTab !== null) return;
    if (!activeCase) return;
    if (
      activeCase.review_status === "needs_input" ||
      activeCase.review_status === "reviewing"
    ) {
      setSidebarTab("review");
    } else {
      setSidebarTab("strategy");
    }
  }, [activeCase, sidebarTab]);

  if (isLoading || !user || !activeCase) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading case...</p>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="shrink-0 border-b bg-white px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div>
              <h1 className="font-semibold">{activeCase.title}</h1>
              <p className="text-xs text-muted-foreground">
                {[activeCase.club_name, activeCase.sport].filter(Boolean).join(" · ")}
              </p>
            </div>
            <Badge>{activeCase.status}</Badge>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push(`/cases/${caseId}/vault`)}
            >
              <Archive className="mr-1 h-4 w-4" /> Vault
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push(`/cases/${caseId}/drafts`)}
            >
              <PenTool className="mr-1 h-4 w-4" /> Drafts
            </Button>
          </div>
        </div>
      </header>

      {/* Main content: chat + sidebar */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Chat */}
        <div className="relative flex-1 border-r">
          <div className="absolute inset-0 flex flex-col">
            <ChatPanel caseId={caseId} />
          </div>
        </div>

        {/* Sidebar */}
        <div className="hidden w-80 overflow-y-auto bg-gray-50 p-4 lg:block">
          {previousVisitedAt !== undefined && (
            <CaseWelcomeBack
              activeCase={activeCase}
              previousVisitedAt={previousVisitedAt}
              onJumpToReview={() => setSidebarTab("review")}
              onJumpToStrategy={() => setSidebarTab("strategy")}
            />
          )}
          <Tabs value={sidebarTab ?? "strategy"} onValueChange={setSidebarTab}>
            <TabsList className="w-full">
              <TabsTrigger value="review" className="flex-1">
                Review
                {(activeCase.review_status === "needs_input" ||
                  activeCase.review_status === "reviewing") && (
                  <span className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">
                    !
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="strategy" className="flex-1">Strategy</TabsTrigger>
              <TabsTrigger value="info" className="flex-1">Info</TabsTrigger>
            </TabsList>

            <TabsContent value="review" className="space-y-4">
              <ReviewPanel
                caseId={caseId}
                reviewStatus={activeCase.review_status}
                onAnyChange={() => loadCase(caseId)}
              />
              <EvidenceRequestPanel
                caseId={caseId}
                onAnyChange={() => loadCase(caseId)}
              />
            </TabsContent>

            <TabsContent value="strategy" className="space-y-4">
              <StrategyPanel
                activeCase={activeCase}
                onCaseChange={() => loadCase(caseId)}
              />
            </TabsContent>

            <TabsContent value="info" className="space-y-4">
              <Card>
                <CardContent className="space-y-3 pt-4 text-sm">
                  {activeCase.category && (
                    <div>
                      <p className="text-xs text-muted-foreground">Category</p>
                      <p>{activeCase.category}</p>
                    </div>
                  )}
                  {activeCase.urgency && (
                    <div>
                      <p className="text-xs text-muted-foreground">Urgency</p>
                      <Badge variant={activeCase.urgency === "critical" ? "destructive" : "outline"}>
                        {activeCase.urgency}
                      </Badge>
                    </div>
                  )}
                  {activeCase.desired_outcome && (
                    <div>
                      <p className="text-xs text-muted-foreground">Desired Outcome</p>
                      <p>{activeCase.desired_outcome}</p>
                    </div>
                  )}
                  {activeCase.description && (
                    <div>
                      <p className="text-xs text-muted-foreground">Description</p>
                      <p className="text-muted-foreground">{activeCase.description}</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
