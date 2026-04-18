"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Plus, FileText, Calendar, Download, ChevronDown, ChevronRight, Paperclip } from "lucide-react";
import type { EvidenceItem, EvidenceRequest, TimelineEvent } from "@/lib/types";

export default function VaultPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params.id as string;
  const { user, isLoading, loadFromStorage } = useAuthStore();
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [requestsById, setRequestsById] = useState<Record<string, EvidenceRequest>>({});
  const [activeTab, setActiveTab] = useState<"evidence" | "timeline">("evidence");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => { loadFromStorage(); }, [loadFromStorage]);

  useEffect(() => {
    if (user && caseId) {
      api.listEvidence(caseId).then((r) => setEvidence(r as unknown as EvidenceItem[]));
      api.getTimeline(caseId).then((r) => setTimeline(r as unknown as TimelineEvent[]));
      api.listEvidenceRequests(caseId).then((rs) => {
        const map: Record<string, EvidenceRequest> = {};
        for (const r of rs) map[r.id] = r;
        setRequestsById(map);
      });
    }
  }, [user, caseId]);

  if (isLoading || !user) return null;

  const typeIcons: Record<string, string> = {
    email: "📧", screenshot: "📷", document: "📄", receipt: "🧾",
    correspondence: "💬", policy: "📋", note: "📝", contract: "📑",
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => router.push(`/cases/${caseId}`)}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h1 className="text-lg font-semibold">Evidence Vault</h1>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              <Download className="mr-1 h-4 w-4" /> Export PDF
            </Button>
            <Button size="sm">
              <Plus className="mr-1 h-4 w-4" /> Add Evidence
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        {/* Tab switcher */}
        <div className="mb-6 flex gap-2">
          <Button
            variant={activeTab === "evidence" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("evidence")}
          >
            <FileText className="mr-1 h-4 w-4" /> Evidence ({evidence.length})
          </Button>
          <Button
            variant={activeTab === "timeline" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("timeline")}
          >
            <Calendar className="mr-1 h-4 w-4" /> Timeline ({timeline.length})
          </Button>
        </div>

        {activeTab === "evidence" ? (
          evidence.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center py-12">
                <FileText className="mb-3 h-10 w-10 text-muted-foreground" />
                <p className="mb-1 font-medium">No evidence yet</p>
                <p className="text-sm text-muted-foreground">
                  Upload documents or the Vault agent will collect evidence during your chat.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {evidence.map((item) => {
                const isExpanded = expandedId === item.id;
                return (
                  <Card
                    key={item.id}
                    className="cursor-pointer transition-shadow hover:shadow-md"
                    onClick={() => setExpandedId(isExpanded ? null : item.id)}
                  >
                    <CardContent className="p-4">
                      <div className="flex items-start gap-3">
                        <span className="text-2xl">{typeIcons[item.evidence_type] || "📎"}</span>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium">{item.title}</h3>
                            <Badge variant="outline" className="text-xs">{item.evidence_type}</Badge>
                          </div>
                          {item.description && (
                            <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
                          )}
                          {item.source_request_id && requestsById[item.source_request_id] && (
                            <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                              <Paperclip className="h-3 w-3" />
                              Provided in response to:{" "}
                              <span className="italic">
                                {requestsById[item.source_request_id].title}
                              </span>
                            </p>
                          )}
                          {item.source_reference && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              Source: {item.source_reference}
                            </p>
                          )}
                          <div className="mt-2 flex gap-1">
                            {item.tags?.map((tag) => (
                              <Badge key={tag} variant="secondary" className="text-xs">{tag}</Badge>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {item.event_date && (
                            <p className="text-xs text-muted-foreground">{item.event_date}</p>
                          )}
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                          )}
                        </div>
                      </div>

                      {isExpanded && item.content && (
                        <div className="mt-4 border-t pt-4">
                          <p className="mb-1 text-xs font-medium text-muted-foreground uppercase">Content</p>
                          <div className="whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">
                            {item.content}
                          </div>
                        </div>
                      )}

                      {isExpanded && item.unanswered_questions && item.unanswered_questions.length > 0 && (
                        <div className="mt-3">
                          <p className="mb-1 text-xs font-medium text-muted-foreground uppercase">Unanswered Questions</p>
                          <ul className="list-inside list-disc text-sm text-muted-foreground">
                            {item.unanswered_questions.map((q, i) => (
                              <li key={i}>{q}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {isExpanded && !item.content && (
                        <div className="mt-4 border-t pt-4">
                          <p className="text-sm text-muted-foreground italic">No full content available for this evidence item.</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )
        ) : (
          timeline.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center py-12">
                <Calendar className="mb-3 h-10 w-10 text-muted-foreground" />
                <p className="mb-1 font-medium">No timeline events yet</p>
                <p className="text-sm text-muted-foreground">
                  Events will be added as you chat and provide evidence.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="relative border-l-2 border-gray-200 pl-6">
              {timeline.map((event) => (
                <div key={event.id} className="relative mb-6 pb-2">
                  <div className="absolute -left-[31px] h-4 w-4 rounded-full border-2 border-primary bg-white" />
                  <p className="text-xs font-medium text-primary">{event.event_date}</p>
                  <p className="mt-1 text-sm">{event.description}</p>
                  {event.source && (
                    <p className="mt-1 text-xs text-muted-foreground">Source: {event.source}</p>
                  )}
                </div>
              ))}
            </div>
          )
        )}
      </main>
    </div>
  );
}
