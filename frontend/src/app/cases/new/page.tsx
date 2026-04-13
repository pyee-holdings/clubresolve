"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useCaseStore } from "@/stores/caseStore";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft } from "lucide-react";

const CATEGORIES = [
  { value: "billing", label: "Billing / Financial" },
  { value: "safety", label: "Athlete Safety" },
  { value: "governance", label: "Governance / Board" },
  { value: "coaching", label: "Coaching" },
  { value: "eligibility", label: "Eligibility / Registration" },
  { value: "other", label: "Other" },
];

const SPORTS = [
  "Soccer", "Hockey", "Gymnastics", "Swimming", "Basketball", "Baseball",
  "Volleyball", "Track & Field", "Lacrosse", "Rugby", "Figure Skating",
  "Tennis", "Martial Arts", "Dance", "Other",
];

const URGENCY = [
  { value: "low", label: "Low", desc: "No time pressure" },
  { value: "medium", label: "Medium", desc: "Should address within weeks" },
  { value: "high", label: "High", desc: "Needs attention this week" },
  { value: "critical", label: "Critical", desc: "Immediate safety or eligibility concern" },
];

const RISK_FLAGS = [
  { value: "athlete_safety", label: "Athlete Safety Concern" },
  { value: "retaliation", label: "Risk of Retaliation" },
  { value: "eligibility", label: "Competition Eligibility Impact" },
  { value: "financial", label: "Financial Pressure" },
  { value: "child_welfare", label: "Child Welfare Concern" },
];

export default function NewCasePage() {
  const router = useRouter();
  const { createCase } = useCaseStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    title: "",
    category: "",
    club_name: "",
    sport: "",
    description: "",
    desired_outcome: "",
    urgency: "medium",
    risk_flags: [] as string[],
    prior_attempts: "",
    timeline_start: "",
  });

  const toggleRiskFlag = (flag: string) => {
    setForm((f) => ({
      ...f,
      risk_flags: f.risk_flags.includes(flag)
        ? f.risk_flags.filter((r) => r !== flag)
        : [...f.risk_flags, flag],
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return setError("Please provide a title for your case");
    setError("");
    setLoading(true);
    try {
      const newCase = await createCase({
        ...form,
        risk_flags: form.risk_flags.length > 0 ? form.risk_flags : null,
      });
      router.push(`/cases/${newCase.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create case");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-6 py-4">
          <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Back
          </Button>
          <h1 className="text-lg font-semibold">New Case</h1>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-8">
        <Card>
          <CardHeader>
            <CardTitle>Case Intake Form</CardTitle>
            <CardDescription>
              Tell us about your situation. The more detail you provide, the better we can help.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <div className="rounded bg-red-50 p-3 text-sm text-red-600">{error}</div>
              )}

              {/* Title */}
              <div className="space-y-2">
                <Label htmlFor="title">Case Title *</Label>
                <Input
                  id="title"
                  placeholder="e.g., Billing dispute with ABC Soccer Club"
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                />
              </div>

              {/* Club + Sport */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="club">Club Name</Label>
                  <Input
                    id="club"
                    placeholder="e.g., Vancouver FC"
                    value={form.club_name}
                    onChange={(e) => setForm((f) => ({ ...f, club_name: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sport">Sport</Label>
                  <select
                    id="sport"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                    value={form.sport}
                    onChange={(e) => setForm((f) => ({ ...f, sport: e.target.value }))}
                  >
                    <option value="">Select sport</option>
                    {SPORTS.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Category */}
              <div className="space-y-2">
                <Label>Issue Category</Label>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((c) => (
                    <Badge
                      key={c.value}
                      variant={form.category === c.value ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => setForm((f) => ({ ...f, category: c.value }))}
                    >
                      {c.label}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Description */}
              <div className="space-y-2">
                <Label htmlFor="description">What happened?</Label>
                <Textarea
                  id="description"
                  placeholder="Describe the situation in as much detail as possible..."
                  rows={5}
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                />
              </div>

              {/* Desired outcome */}
              <div className="space-y-2">
                <Label htmlFor="outcome">What outcome are you looking for?</Label>
                <Textarea
                  id="outcome"
                  placeholder="e.g., Full refund, policy change, apology, safety measures..."
                  rows={2}
                  value={form.desired_outcome}
                  onChange={(e) => setForm((f) => ({ ...f, desired_outcome: e.target.value }))}
                />
              </div>

              {/* Urgency */}
              <div className="space-y-2">
                <Label>Urgency</Label>
                <div className="grid gap-2 sm:grid-cols-4">
                  {URGENCY.map((u) => (
                    <div
                      key={u.value}
                      className={`cursor-pointer rounded-lg border p-3 text-center transition-colors ${
                        form.urgency === u.value
                          ? "border-primary bg-primary/5"
                          : "hover:bg-gray-50"
                      }`}
                      onClick={() => setForm((f) => ({ ...f, urgency: u.value }))}
                    >
                      <p className="text-sm font-medium">{u.label}</p>
                      <p className="text-xs text-muted-foreground">{u.desc}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Risk flags */}
              <div className="space-y-2">
                <Label>Risk Flags (select all that apply)</Label>
                <div className="flex flex-wrap gap-2">
                  {RISK_FLAGS.map((rf) => (
                    <Badge
                      key={rf.value}
                      variant={form.risk_flags.includes(rf.value) ? "destructive" : "outline"}
                      className="cursor-pointer"
                      onClick={() => toggleRiskFlag(rf.value)}
                    >
                      {rf.label}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Prior attempts */}
              <div className="space-y-2">
                <Label htmlFor="prior">Have you already tried to resolve this?</Label>
                <Textarea
                  id="prior"
                  placeholder="Describe any previous attempts to address this issue..."
                  rows={2}
                  value={form.prior_attempts}
                  onChange={(e) => setForm((f) => ({ ...f, prior_attempts: e.target.value }))}
                />
              </div>

              {/* Timeline */}
              <div className="space-y-2">
                <Label htmlFor="timeline">When did this start?</Label>
                <Input
                  id="timeline"
                  type="date"
                  value={form.timeline_start}
                  onChange={(e) => setForm((f) => ({ ...f, timeline_start: e.target.value }))}
                />
              </div>

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Creating case..." : "Create Case & Start"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
