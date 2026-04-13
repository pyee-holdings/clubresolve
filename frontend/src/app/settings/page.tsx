"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Key, Check, X, Loader2 } from "lucide-react";
import type { APIKeyConfig } from "@/lib/types";

const PROVIDERS = [
  {
    id: "anthropic",
    name: "Anthropic (Claude)",
    placeholder: "sk-ant-...",
    models: ["claude-sonnet-4-20250514", "claude-haiku-4-20250414"],
  },
  {
    id: "openai",
    name: "OpenAI (GPT)",
    placeholder: "sk-...",
    models: ["gpt-4o", "gpt-4o-mini"],
  },
  {
    id: "google",
    name: "Google (Gemini)",
    placeholder: "AIza...",
    models: ["gemini-2.5-pro", "gemini-2.0-flash"],
  },
];

export default function SettingsPage() {
  const router = useRouter();
  const { user, isLoading, loadFromStorage } = useAuthStore();
  const [keys, setKeys] = useState<APIKeyConfig[]>([]);
  const [newKey, setNewKey] = useState({ provider: "", key: "" });
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  useEffect(() => {
    if (user) loadKeys();
  }, [user]);

  const loadKeys = async () => {
    try {
      const result = (await api.listApiKeys()) as APIKeyConfig[];
      setKeys(result);
    } catch {}
  };

  const handleSave = async (providerId: string, apiKey: string) => {
    setSaving(true);
    setMessage("");
    try {
      // Validate first
      setValidating(true);
      const { valid } = (await api.validateApiKey(providerId, apiKey)) as { valid: boolean };
      setValidating(false);

      if (!valid) {
        setMessage("Invalid API key. Please check and try again.");
        setSaving(false);
        return;
      }

      await api.saveApiKey(providerId, apiKey);
      setMessage("API key saved successfully!");
      setNewKey({ provider: "", key: "" });
      await loadKeys();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
      setValidating(false);
    }
  };

  const handleDelete = async (provider: string) => {
    try {
      await api.deleteApiKey(provider);
      await loadKeys();
    } catch {}
  };

  if (isLoading || !user) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-6 py-4">
          <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Back
          </Button>
          <h1 className="text-lg font-semibold">Settings</h1>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-6 px-6 py-8">
        {/* Configured Keys */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="h-5 w-5" /> LLM API Keys
            </CardTitle>
            <CardDescription>
              Configure your own API keys. Your keys are encrypted and never shared. You pay your
              own LLM provider directly.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {keys.length > 0 && (
              <div className="space-y-2">
                {keys.map((k) => (
                  <div key={k.id} className="flex items-center justify-between rounded-lg border p-3">
                    <div className="flex items-center gap-3">
                      <Check className="h-4 w-4 text-green-500" />
                      <div>
                        <p className="text-sm font-medium">
                          {PROVIDERS.find((p) => p.id === k.provider)?.name || k.provider}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {k.preferred_model || "Default model"} · {k.model_tier}
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(k.provider)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {/* Add new key */}
            <div className="rounded-lg border border-dashed p-4">
              <p className="mb-3 text-sm font-medium">Add API Key</p>
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {PROVIDERS.map((p) => (
                    <Badge
                      key={p.id}
                      variant={newKey.provider === p.id ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => setNewKey((k) => ({ ...k, provider: p.id }))}
                    >
                      {p.name}
                    </Badge>
                  ))}
                </div>
                {newKey.provider && (
                  <>
                    <div className="space-y-2">
                      <Label>API Key</Label>
                      <Input
                        type="password"
                        placeholder={
                          PROVIDERS.find((p) => p.id === newKey.provider)?.placeholder || "Enter key"
                        }
                        value={newKey.key}
                        onChange={(e) => setNewKey((k) => ({ ...k, key: e.target.value }))}
                      />
                    </div>
                    <Button
                      onClick={() => handleSave(newKey.provider, newKey.key)}
                      disabled={!newKey.key || saving}
                    >
                      {validating ? (
                        <>
                          <Loader2 className="mr-1 h-4 w-4 animate-spin" /> Validating...
                        </>
                      ) : saving ? (
                        "Saving..."
                      ) : (
                        "Validate & Save"
                      )}
                    </Button>
                  </>
                )}
              </div>
              {message && (
                <p className={`mt-2 text-sm ${message.includes("success") ? "text-green-600" : "text-red-600"}`}>
                  {message}
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Account info */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Account</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p><strong>Name:</strong> {user.name}</p>
            <p><strong>Email:</strong> {user.email}</p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
