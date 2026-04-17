"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { useCaseStore } from "@/stores/caseStore";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Plus, Settings, Shield, FileText, Scale, PenTool, Trash2, Sparkles } from "lucide-react";

export default function Dashboard() {
  const router = useRouter();
  const { user, isLoading, loadFromStorage, logout } = useAuthStore();
  const { cases, loadCases, deleteCase } = useCaseStore();

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/auth/login");
    } else if (user) {
      loadCases();
    }
  }, [user, isLoading, router, loadCases]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!user) return null;

  const statusColors: Record<string, string> = {
    intake: "bg-blue-100 text-blue-800",
    researching: "bg-yellow-100 text-yellow-800",
    planning: "bg-purple-100 text-purple-800",
    active: "bg-green-100 text-green-800",
    escalating: "bg-orange-100 text-orange-800",
    resolved: "bg-gray-100 text-gray-600",
    closed: "bg-gray-100 text-gray-400",
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">ClubResolve</h1>
            <p className="text-sm text-muted-foreground">Sports Club Advocacy Support</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{user.name}</span>
            <Button variant="outline" size="sm" onClick={() => router.push("/settings")}>
              <Settings className="mr-1 h-4 w-4" /> Settings
            </Button>
            <Button variant="ghost" size="sm" onClick={logout}>
              Sign Out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {/* Disclaimer */}
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm text-amber-800">
            <strong>Important:</strong> ClubResolve is a case organization and advocacy support
            tool. It does not provide legal advice. For formal legal matters, please consult a
            qualified lawyer.
          </p>
        </div>

        {/* Module cards */}
        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card
            className="cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => router.push("/cases/new")}
          >
            <CardContent className="flex items-center gap-3 p-4">
              <div className="rounded-lg bg-blue-100 p-2">
                <Plus className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="font-medium">New Case</p>
                <p className="text-xs text-muted-foreground">Start a new dispute case</p>
              </div>
            </CardContent>
          </Card>
          <Card
            className="cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => router.push("/wizard")}
          >
            <CardContent className="flex items-center gap-3 p-4">
              <div className="rounded-lg bg-indigo-100 p-2">
                <Sparkles className="h-5 w-5 text-indigo-600" />
              </div>
              <div>
                <p className="font-medium">Action Plan Wizard</p>
                <p className="text-xs text-muted-foreground">6 questions → personalized plan</p>
              </div>
            </CardContent>
          </Card>
          {[
            { icon: Shield, color: "purple", name: "Navigator", desc: "Strategy & action planning" },
            { icon: Scale, color: "green", name: "Counsel", desc: "Policy & governance research" },
            { icon: PenTool, color: "orange", name: "Draft Studio", desc: "Communications & letters" },
          ].map((m) => (
            <Card key={m.name} className="opacity-80">
              <CardContent className="flex items-center gap-3 p-4">
                <div className={`rounded-lg bg-${m.color}-100 p-2`}>
                  <m.icon className={`h-5 w-5 text-${m.color}-600`} />
                </div>
                <div>
                  <p className="font-medium">{m.name}</p>
                  <p className="text-xs text-muted-foreground">{m.desc}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Cases list */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Your Cases</h2>
          <Button onClick={() => router.push("/cases/new")}>
            <Plus className="mr-1 h-4 w-4" /> New Case
          </Button>
        </div>

        {cases.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <FileText className="mb-4 h-12 w-12 text-muted-foreground" />
              <p className="mb-2 font-medium">No cases yet</p>
              <p className="mb-4 text-sm text-muted-foreground">
                Start a new case to get help with a sports club dispute
              </p>
              <Button onClick={() => router.push("/cases/new")}>
                <Plus className="mr-1 h-4 w-4" /> Create Your First Case
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {cases.map((c) => (
              <Card
                key={c.id}
                className="cursor-pointer transition-shadow hover:shadow-md"
                onClick={() => router.push(`/cases/${c.id}`)}
              >
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium">{c.title}</h3>
                      <Badge className={statusColors[c.status] || ""}>{c.status}</Badge>
                      {(c.urgency === "high" || c.urgency === "critical") && (
                        <Badge variant="destructive">{c.urgency}</Badge>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {[c.club_name, c.sport, c.category].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <p className="text-xs text-muted-foreground">
                      {new Date(c.updated_at).toLocaleDateString()}
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-red-600"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm("Delete this case? This cannot be undone.")) {
                          deleteCase(c.id);
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
