"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { EvidenceRequest } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Loader2,
  Paperclip,
  Type,
  X,
  AlertCircle,
} from "lucide-react";

interface Props {
  caseId: string;
  onAnyChange?: () => void;
}

type FulfillMode = "none" | "file" | "text";

const PRIORITY_STYLES: Record<
  EvidenceRequest["priority"],
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

const TYPE_LABELS: Record<string, string> = {
  email: "Email",
  screenshot: "Screenshot",
  document: "Document",
  receipt: "Receipt",
  correspondence: "Correspondence",
  policy: "Policy / bylaw",
  note: "Note",
  contract: "Contract",
  testimony: "Testimony / statement",
  other: "Other",
};

function priorityOrder(r: EvidenceRequest): number {
  return r.priority === "critical" ? 0 : r.priority === "important" ? 1 : 2;
}

export function EvidenceRequestPanel({ caseId, onAnyChange }: Props) {
  const [items, setItems] = useState<EvidenceRequest[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-request editing state
  const [modeByRequest, setModeByRequest] = useState<Record<string, FulfillMode>>({});
  const [textDraftByRequest, setTextDraftByRequest] = useState<Record<string, string>>({});
  const [fileByRequest, setFileByRequest] = useState<Record<string, File | null>>({});
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});

  const refresh = useCallback(async () => {
    try {
      const rows = await api.listEvidenceRequests(caseId);
      setItems(rows);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load evidence requests");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setMode = (id: string, mode: FulfillMode) =>
    setModeByRequest((m) => ({ ...m, [id]: mode }));

  const handleSubmitText = async (r: EvidenceRequest) => {
    const content = (textDraftByRequest[r.id] ?? "").trim();
    if (!content) return;
    setSubmittingId(r.id);
    try {
      const updated = await api.fulfillEvidenceRequestText(caseId, r.id, { content });
      setItems((prev) =>
        prev ? prev.map((it) => (it.id === r.id ? updated : it)) : prev,
      );
      setMode(r.id, "none");
      setTextDraftByRequest((d) => {
        const n = { ...d };
        delete n[r.id];
        return n;
      });
      onAnyChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSubmittingId(null);
    }
  };

  const handleSubmitFile = async (r: EvidenceRequest) => {
    const file = fileByRequest[r.id];
    if (!file) return;
    setSubmittingId(r.id);
    try {
      const updated = await api.fulfillEvidenceRequestFile(caseId, r.id, file);
      setItems((prev) =>
        prev ? prev.map((it) => (it.id === r.id ? updated : it)) : prev,
      );
      setMode(r.id, "none");
      setFileByRequest((f) => ({ ...f, [r.id]: null }));
      onAnyChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setSubmittingId(null);
    }
  };

  const handleUnavailable = async (r: EvidenceRequest) => {
    setSubmittingId(r.id);
    try {
      const updated = await api.markEvidenceRequestUnavailable(caseId, r.id);
      setItems((prev) =>
        prev ? prev.map((it) => (it.id === r.id ? updated : it)) : prev,
      );
      onAnyChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSubmittingId(null);
    }
  };

  if (loading && items === null) {
    return (
      <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading evidence requests...
      </div>
    );
  }

  if (!items || items.length === 0) return null;

  const open = items
    .filter((r) => r.status === "open")
    .sort((a, b) => priorityOrder(a) - priorityOrder(b));
  const resolved = items.filter((r) => r.status !== "open");

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
          {error}
        </div>
      )}

      <h3 className="flex items-center gap-1 text-sm font-semibold">
        <Paperclip className="h-4 w-4" />
        {open.length > 0
          ? `${open.length} piece${open.length === 1 ? "" : "s"} of evidence to gather`
          : "All evidence requests resolved"}
      </h3>

      {open.map((r) => {
        const p = PRIORITY_STYLES[r.priority];
        const mode = modeByRequest[r.id] ?? "none";
        const textDraft = textDraftByRequest[r.id] ?? "";
        const pickedFile = fileByRequest[r.id] ?? null;
        const isSubmitting = submittingId === r.id;
        return (
          <Card key={r.id}>
            <CardHeader className="pb-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className={`text-[10px] ${p.className}`}>
                  {r.priority === "critical" && (
                    <AlertTriangle className="mr-1 h-3 w-3" />
                  )}
                  {p.label}
                </Badge>
                <Badge variant="secondary" className="text-[10px]">
                  {TYPE_LABELS[r.evidence_type] ?? r.evidence_type}
                </Badge>
                {r.expected_date && (
                  <Badge variant="outline" className="text-[10px]">
                    {r.expected_date}
                  </Badge>
                )}
              </div>
              <CardTitle className="mt-2 text-sm leading-snug">{r.title}</CardTitle>
              {r.description && (
                <p className="text-xs text-muted-foreground">{r.description}</p>
              )}
            </CardHeader>
            <CardContent className="space-y-2">
              {mode === "none" && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setMode(r.id, "file")}
                    disabled={isSubmitting}
                  >
                    <Paperclip className="mr-1 h-3 w-3" /> Attach file
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setMode(r.id, "text")}
                    disabled={isSubmitting}
                  >
                    <Type className="mr-1 h-3 w-3" /> Paste text
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleUnavailable(r)}
                    disabled={isSubmitting}
                  >
                    <AlertCircle className="mr-1 h-3 w-3" /> Don&apos;t have it
                  </Button>
                </div>
              )}

              {mode === "text" && (
                <div className="space-y-2">
                  <Textarea
                    rows={4}
                    value={textDraft}
                    placeholder="Paste the email body, quote the relevant section, or describe what it says..."
                    onChange={(e) =>
                      setTextDraftByRequest((d) => ({ ...d, [r.id]: e.target.value }))
                    }
                    disabled={isSubmitting}
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setMode(r.id, "none")}
                      disabled={isSubmitting}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleSubmitText(r)}
                      disabled={isSubmitting || textDraft.trim().length === 0}
                    >
                      {isSubmitting && (
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      )}
                      Save evidence
                    </Button>
                  </div>
                </div>
              )}

              {mode === "file" && (
                <div className="space-y-2">
                  <Input
                    type="file"
                    ref={(el) => {
                      fileInputs.current[r.id] = el;
                    }}
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      setFileByRequest((m) => ({ ...m, [r.id]: f }));
                    }}
                    disabled={isSubmitting}
                  />
                  {pickedFile && (
                    <p className="text-xs text-muted-foreground">
                      Selected: {pickedFile.name}
                    </p>
                  )}
                  <div className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setMode(r.id, "none");
                        setFileByRequest((m) => ({ ...m, [r.id]: null }));
                        if (fileInputs.current[r.id]) {
                          fileInputs.current[r.id]!.value = "";
                        }
                      }}
                      disabled={isSubmitting}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleSubmitFile(r)}
                      disabled={isSubmitting || !pickedFile}
                    >
                      {isSubmitting && (
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      )}
                      Upload
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}

      {resolved.length > 0 && (
        <div className="space-y-2 pt-3">
          <h4 className="text-xs font-medium text-muted-foreground">
            Provided / resolved ({resolved.length})
          </h4>
          {resolved.map((r) => {
            const statusLabel =
              r.status === "fulfilled"
                ? "Fulfilled"
                : r.status === "unavailable"
                ? "Not available"
                : "Dismissed";
            const StatusIcon =
              r.status === "fulfilled"
                ? CheckCircle2
                : r.status === "unavailable"
                ? AlertCircle
                : X;
            const iconColor =
              r.status === "fulfilled"
                ? "text-emerald-500"
                : "text-muted-foreground";
            return (
              <Card key={r.id} className="bg-muted/30">
                <CardContent className="space-y-1 py-3 text-xs">
                  <div className="flex items-center gap-2">
                    <StatusIcon className={`h-3 w-3 ${iconColor}`} />
                    <p className="font-medium">{r.title}</p>
                    <Badge variant="outline" className="ml-auto text-[10px]">
                      {statusLabel}
                    </Badge>
                  </div>
                  {r.status === "fulfilled" && (
                    <p className="pl-5 text-muted-foreground">
                      <FileText className="mr-1 inline h-3 w-3" /> Saved to vault
                    </p>
                  )}
                  {r.unavailable_reason && (
                    <p className="pl-5 text-muted-foreground">
                      {r.unavailable_reason}
                    </p>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
