"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft,
  ArrowRight,
  Printer,
  Copy,
  Check,
  RotateCcw,
  Loader2,
  AlertTriangle,
  Scale,
} from "lucide-react";

// ── Constants ──────────────────────────────────────────────

const CATEGORIES = [
  {
    value: "governance",
    label: "Governance / Board Decision",
    desc: "Board made a decision without following proper process",
  },
  {
    value: "billing",
    label: "Billing / Financial",
    desc: "Fee disputes, refunds, unexplained charges, financial transparency",
  },
  {
    value: "safety",
    label: "Athlete Safety",
    desc: "Coaching behavior, facility issues, SafeSport violations",
  },
  {
    value: "coaching",
    label: "Coaching Decisions",
    desc: "Playing time, roster cuts, team placement without explanation",
  },
  {
    value: "eligibility",
    label: "Eligibility / Registration",
    desc: "Registration issues, transfer problems, eligibility disputes",
  },
  {
    value: "discipline",
    label: "Unfair Discipline",
    desc: "Suspension or expulsion without proper process",
  },
  {
    value: "other",
    label: "Other",
    desc: "My situation doesn't fit these categories",
  },
];

const SPORTS = [
  "Soccer",
  "Hockey",
  "Gymnastics",
  "Swimming",
  "Basketball",
  "Baseball",
  "Volleyball",
  "Track & Field",
  "Lacrosse",
  "Rugby",
  "Figure Skating",
  "Tennis",
  "Martial Arts",
  "Dance",
  "Other",
];

const TRIED_OPTIONS = [
  {
    value: "nothing",
    label: "Haven't tried anything yet",
    desc: "This is my first step",
  },
  {
    value: "verbal",
    label: "Spoke to coach or staff",
    desc: "Had a conversation but nothing changed",
  },
  {
    value: "written",
    label: "Sent a written complaint",
    desc: "Emailed or wrote to the club",
  },
  {
    value: "board",
    label: "Complained to the board",
    desc: "Raised the issue with club directors",
  },
  {
    value: "other",
    label: "Other",
    desc: "Something else",
  },
];

const OUTCOME_OPTIONS = [
  {
    value: "records",
    label: "Get access to club records",
    desc: "Meeting minutes, financial statements, member register",
  },
  {
    value: "reversal",
    label: "Reverse a decision",
    desc: "Undo a board decision, reinstate membership, restore playing time",
  },
  {
    value: "refund",
    label: "Get a refund",
    desc: "Recover fees or charges",
  },
  {
    value: "accountability",
    label: "Hold the board accountable",
    desc: "Ensure the club follows its own rules going forward",
  },
  {
    value: "safety",
    label: "Address a safety concern",
    desc: "Ensure a safe environment for my child",
  },
  {
    value: "other",
    label: "Other",
    desc: "Something else",
  },
];

const DISCLAIMER =
  "ClubResolve provides advocacy support and general information about your rights as a member of a BC registered society. This is NOT legal advice. ClubResolve is not a law firm and does not replace consultation with a qualified lawyer. The information and templates provided are for educational and self-advocacy purposes only. Laws and bylaws vary — verify all citations against current legislation before taking action.";

const PROGRESS_MESSAGES = [
  "Understanding your situation...",
  "Researching relevant policies...",
  "Identifying your rights...",
  "Building your action plan...",
];

// ── Types ──────────────────────────────────────────────────

interface ActionStep {
  title: string;
  description: string;
  citation: string;
  template: string;
  deadline: string;
}

interface EscalationStep {
  if: string;
  then: string;
  deadline: string;
}

interface ActionPlan {
  summary: string;
  steps: ActionStep[];
  escalation_timeline: EscalationStep[];
  disclaimer: string;
}

// ── Component ──────────────────────────────────────────────

export default function WizardPage() {
  const router = useRouter();
  const { user, isLoading, loadFromStorage } = useAuthStore();

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  // Form state
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    province: "BC",
    sport: "",
    sportOther: "",
    category: "",
    categoryOther: "",
    tried: "",
    triedOther: "",
    desired_outcome: "",
    outcomeOther: "",
    description: "",
    email: "",
  });

  // Result state
  const [loading, setLoading] = useState(false);
  const [progressIdx, setProgressIdx] = useState(0);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const progressInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle>Sign in required</CardTitle>
            <CardDescription>
              You need to be logged in with an API key configured to use the
              Action Plan Wizard.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => router.push("/auth/login")} className="w-full">
              Sign In
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const totalSteps = 6;

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    setProgressIdx(0);

    // Animate progress messages
    progressInterval.current = setInterval(() => {
      setProgressIdx((prev) =>
        prev < PROGRESS_MESSAGES.length - 1 ? prev + 1 : prev
      );
    }, 2500);

    try {
      const result = await api.generateActionPlan({
        province: form.province,
        sport: form.sport === "Other" ? form.sportOther : form.sport,
        category: form.category === "other" ? form.categoryOther : form.category,
        tried: form.tried === "other" ? form.triedOther : form.tried,
        desired_outcome:
          form.desired_outcome === "other"
            ? form.outcomeOther
            : form.desired_outcome,
        description: form.description,
        email: form.email,
      });
      setPlan(result);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Something went wrong";
      setError(msg);
    } finally {
      setLoading(false);
      if (progressInterval.current) {
        clearInterval(progressInterval.current);
        progressInterval.current = null;
      }
    }
  };

  const handleCopy = async (text: string, idx: number) => {
    await navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const handleStartOver = () => {
    setPlan(null);
    setError("");
    setStep(0);
    setForm({
      province: "BC",
      sport: "",
      sportOther: "",
      category: "",
      categoryOther: "",
      tried: "",
      triedOther: "",
      desired_outcome: "",
      outcomeOther: "",
      description: "",
      email: "",
    });
  };

  const canAdvance = () => {
    switch (step) {
      case 0:
        return form.province.length > 0;
      case 1:
        return form.sport.length > 0 && (form.sport !== "Other" || form.sportOther.length > 0);
      case 2:
        return form.category.length > 0 && (form.category !== "other" || form.categoryOther.length > 0);
      case 3:
        return form.tried.length > 0 && (form.tried !== "other" || form.triedOther.length > 0);
      case 4:
        return form.desired_outcome.length > 0 && (form.desired_outcome !== "other" || form.outcomeOther.length > 0);
      case 5:
        return true; // free text is optional
      default:
        return false;
    }
  };

  // ── Loading State ──────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-8 pb-8 flex flex-col items-center gap-4">
            <Loader2 className="h-10 w-10 animate-spin text-primary" />
            <p className="text-lg font-medium animate-pulse">
              {PROGRESS_MESSAGES[progressIdx]}
            </p>
            <p className="text-sm text-muted-foreground">
              This usually takes 5-10 seconds
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── Results Display ────────────────────────────────

  if (plan) {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-2xl mx-auto p-4 py-8">
          {/* Disclaimer banner */}
          <div className="flex items-start gap-2 p-3 mb-6 rounded-md bg-amber-50 border border-amber-200 text-sm text-amber-800 print:bg-white print:border-black">
            <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
            <p>{DISCLAIMER}</p>
          </div>

          {/* Summary — the parent sees this first */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold mb-2">Your Action Plan</h1>
            <p className="text-lg text-muted-foreground">{plan.summary}</p>
          </div>

          {/* Steps */}
          <div className="space-y-4 mb-8">
            {plan.steps.map((s, i) => (
              <Card key={i} className={i === 0 ? "border-primary border-2" : ""}>
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <Badge variant={i === 0 ? "default" : "secondary"}>
                      Step {i + 1}
                    </Badge>
                    <CardTitle className="text-base">{s.title}</CardTitle>
                  </div>
                  {s.deadline && (
                    <CardDescription>{s.deadline}</CardDescription>
                  )}
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm">{s.description}</p>
                  {s.citation && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <Scale className="h-3 w-3" />
                      {s.citation}
                    </p>
                  )}
                  {s.template && (
                    <div className="mt-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                          Template
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleCopy(s.template, i)}
                          className="h-7 text-xs"
                        >
                          {copiedIdx === i ? (
                            <>
                              <Check className="h-3 w-3 mr-1" /> Copied
                            </>
                          ) : (
                            <>
                              <Copy className="h-3 w-3 mr-1" /> Copy
                            </>
                          )}
                        </Button>
                      </div>
                      <pre className="text-xs bg-muted p-3 rounded-md whitespace-pre-wrap font-mono overflow-x-auto">
                        {s.template}
                      </pre>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Escalation Timeline */}
          {plan.escalation_timeline.length > 0 && (
            <div className="mb-8">
              <h2 className="text-lg font-semibold mb-3">
                If things don&apos;t work out...
              </h2>
              <div className="space-y-2">
                {plan.escalation_timeline.map((e, i) => (
                  <div
                    key={i}
                    className="flex gap-3 p-3 bg-muted/50 rounded-md text-sm"
                  >
                    <div className="font-medium text-muted-foreground min-w-[60px]">
                      {e.deadline || `Step ${i + 1}`}
                    </div>
                    <div>
                      <span className="text-muted-foreground">If </span>
                      {e.if}
                      <span className="text-muted-foreground"> → </span>
                      {e.then}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2 mt-6 print:hidden">
            <Button onClick={() => window.print()} variant="outline">
              <Printer className="h-4 w-4 mr-2" />
              Print / Save as PDF
            </Button>
            <Button onClick={handleStartOver} variant="outline">
              <RotateCcw className="h-4 w-4 mr-2" />
              Start Over
            </Button>
            <Button onClick={() => router.push("/")} variant="ghost">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Dashboard
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ── Intake Form ────────────────────────────────────

  const renderStep = () => {
    switch (step) {
      case 0:
        return (
          <>
            <h2 className="text-lg font-semibold mb-4">
              Where is your sports club located?
            </h2>
            <div className="space-y-2">
              {["BC"].map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setForm({ ...form, province: p })}
                  className={`w-full text-left p-3 rounded-md border transition-colors ${
                    form.province === p
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="font-medium">British Columbia</div>
                  <div className="text-sm text-muted-foreground">
                    Currently supporting BC sports clubs
                  </div>
                </button>
              ))}
            </div>
          </>
        );
      case 1:
        return (
          <>
            <h2 className="text-lg font-semibold mb-4">What sport?</h2>
            <div className="grid grid-cols-2 gap-2">
              {SPORTS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setForm({ ...form, sport: s })}
                  className={`text-left p-3 rounded-md border text-sm transition-colors ${
                    form.sport === s
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            {form.sport === "Other" && (
              <Input
                className="mt-3"
                placeholder="What sport?"
                value={form.sportOther}
                onChange={(e) =>
                  setForm({ ...form, sportOther: e.target.value })
                }
                maxLength={100}
              />
            )}
          </>
        );
      case 2:
        return (
          <>
            <h2 className="text-lg font-semibold mb-4">
              What best describes your situation?
            </h2>
            <div className="space-y-2">
              {CATEGORIES.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setForm({ ...form, category: c.value })}
                  className={`w-full text-left p-3 rounded-md border transition-colors ${
                    form.category === c.value
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="font-medium">{c.label}</div>
                  <div className="text-sm text-muted-foreground">{c.desc}</div>
                </button>
              ))}
            </div>
            {form.category === "other" && (
              <Textarea
                className="mt-3"
                placeholder="Describe your situation..."
                value={form.categoryOther}
                onChange={(e) =>
                  setForm({ ...form, categoryOther: e.target.value })
                }
                maxLength={500}
              />
            )}
          </>
        );
      case 3:
        return (
          <>
            <h2 className="text-lg font-semibold mb-4">
              What have you already tried?
            </h2>
            <div className="space-y-2">
              {TRIED_OPTIONS.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setForm({ ...form, tried: t.value })}
                  className={`w-full text-left p-3 rounded-md border transition-colors ${
                    form.tried === t.value
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="font-medium">{t.label}</div>
                  <div className="text-sm text-muted-foreground">{t.desc}</div>
                </button>
              ))}
            </div>
            {form.tried === "other" && (
              <Textarea
                className="mt-3"
                placeholder="What have you tried so far?"
                value={form.triedOther}
                onChange={(e) =>
                  setForm({ ...form, triedOther: e.target.value })
                }
                maxLength={500}
              />
            )}
          </>
        );
      case 4:
        return (
          <>
            <h2 className="text-lg font-semibold mb-4">
              What outcome are you looking for?
            </h2>
            <div className="space-y-2">
              {OUTCOME_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() =>
                    setForm({ ...form, desired_outcome: o.value })
                  }
                  className={`w-full text-left p-3 rounded-md border transition-colors ${
                    form.desired_outcome === o.value
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="font-medium">{o.label}</div>
                  <div className="text-sm text-muted-foreground">{o.desc}</div>
                </button>
              ))}
            </div>
            {form.desired_outcome === "other" && (
              <Textarea
                className="mt-3"
                placeholder="What outcome would you like?"
                value={form.outcomeOther}
                onChange={(e) =>
                  setForm({ ...form, outcomeOther: e.target.value })
                }
                maxLength={500}
              />
            )}
          </>
        );
      case 5:
        return (
          <>
            <h2 className="text-lg font-semibold mb-4">
              Anything else we should know?
            </h2>
            <Textarea
              placeholder="Describe your situation in your own words. Include any details that might help us give better guidance — dates, specific incidents, what was said, etc."
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
              rows={6}
              maxLength={2000}
            />
            <p className="text-xs text-muted-foreground mt-1">
              {form.description.length}/2000 characters
            </p>

            <div className="mt-6">
              <Label htmlFor="email">
                Email (optional, for follow-up)
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="your@email.com"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">
                We&apos;ll check in after 7 days to see if you took the first
                step. No spam, ever.
              </p>
            </div>
          </>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-xl mx-auto p-4 py-8">
        {/* Header */}
        <div className="mb-6">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/")}
            className="mb-2"
          >
            <ArrowLeft className="h-4 w-4 mr-1" />
            Dashboard
          </Button>
          <h1 className="text-2xl font-bold">Action Plan Wizard</h1>
          <p className="text-muted-foreground">
            Answer 6 questions, get a personalized action plan
          </p>
        </div>

        {/* Disclaimer */}
        <div className="flex items-start gap-2 p-3 mb-6 rounded-md bg-amber-50 border border-amber-200 text-xs text-amber-800">
          <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" />
          <p>{DISCLAIMER}</p>
        </div>

        {/* Progress */}
        <div className="flex gap-1.5 mb-6">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <div
              key={i}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                i < step
                  ? "bg-primary"
                  : i === step
                  ? "bg-primary/60"
                  : "bg-muted"
              }`}
            />
          ))}
        </div>

        {/* Error */}
        {error && (
          <div className="p-3 mb-4 rounded-md bg-destructive/10 border border-destructive/20 text-sm text-destructive">
            {error}
            <Button
              size="sm"
              variant="outline"
              className="ml-2"
              onClick={handleSubmit}
            >
              Retry
            </Button>
          </div>
        )}

        {/* Step content */}
        <Card>
          <CardContent className="pt-6">{renderStep()}</CardContent>
        </Card>

        {/* Navigation */}
        <div className="flex justify-between mt-4">
          <Button
            variant="outline"
            onClick={() => setStep(step - 1)}
            disabled={step === 0}
          >
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back
          </Button>

          {step < totalSteps - 1 ? (
            <Button onClick={() => setStep(step + 1)} disabled={!canAdvance()}>
              Next
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={!canAdvance()}>
              Generate Action Plan
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
