"use client";

import * as React from "react";
import { PlaygroundInput, type PlaygroundForm } from "@/components/playground/playground-input";
import { PlaygroundResults } from "@/components/playground/playground-results";
import { analyseMessage, type AnalyseResult } from "@/lib/mockApi";
import { useSignalStore } from "@/stores/signal-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * PlaygroundView — two-pane sandbox for ad-hoc message analysis.
 * Left: input form (message, sample buttons, meta, analyse/clear).
 * Right: animated score countup + intent / confidence / keywords /
 * breakdown / language / risk / drafted reply / why-this-score /
 * compare-to-queue.
 */
const EMPTY_FORM: PlaygroundForm = {
  message: "",
  platform: "discord",
  country: "US",
  community: "r/predictiongames",
  url: "https://joinallbettors.example",
};

export function PlaygroundView() {
  const [form, setForm] = React.useState<PlaygroundForm>(EMPTY_FORM);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<AnalyseResult | null>(null);
  const [announcement, setAnnouncement] = React.useState<string>("");

  const hydrate = useSignalStore((s) => s.hydrate);

  React.useEffect(() => {
    hydrate();
  }, [hydrate]);

  const onFormChange = React.useCallback(
    (patch: Partial<PlaygroundForm>) => {
      setForm((f) => ({ ...f, ...patch }));
    },
    [],
  );

  const handleAnalyse = React.useCallback(async () => {
    if (!form.message.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const r = await analyseMessage(form.message, {
        platform: form.platform,
        country: form.country,
        community: form.community,
        url: form.url,
      });
      setResult(r);
      setAnnouncement(
        `Analysis complete. Score ${r.score}. Intent: ${r.intent}.`,
      );
    } catch {
      setAnnouncement("Analysis failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [form]);

  const handleClear = React.useCallback(() => {
    setForm(EMPTY_FORM);
    setResult(null);
    setLoading(false);
    setAnnouncement("Cleared.");
  }, []);

  // Cmd/Ctrl+Enter triggers Analyse.
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void handleAnalyse();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleAnalyse]);

  return (
    <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      {/* Left — input */}
      <Card className="h-fit lg:sticky lg:top-0">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Playground</CardTitle>
          <p className="text-xs text-text-muted">
            Run any message through the scoring engine.
          </p>
        </CardHeader>
        <CardContent>
          <PlaygroundInput
            form={form}
            onFormChange={onFormChange}
            onAnalyse={handleAnalyse}
            onClear={handleClear}
            loading={loading}
          />
        </CardContent>
      </Card>

      {/* Right — results */}
      <Card className="min-h-full">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Results</CardTitle>
          <p className="text-xs text-text-muted">
            Score, intent, confidence, reply draft and scoring breakdown.
          </p>
        </CardHeader>
        <CardContent>
          <PlaygroundResults loading={loading} result={result} />
        </CardContent>
      </Card>

      {/* sr-only live region */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {announcement}
      </div>
    </div>
  );
}
