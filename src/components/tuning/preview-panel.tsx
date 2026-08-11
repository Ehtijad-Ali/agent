"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import { scoreMessage } from "@/lib/scoring";
import { PreviewCard } from "./preview-card";

/**
 * PreviewPanel — right-hand sticky pane. Re-renders whenever the store's
 * previewSamples change (the store auto-re-scores 8 sample conversations
 * on every setDraftConfig / commitConfig / discardConfig).
 *
 * For each sample we re-score the same message against the COMMITTED config
 * to derive a baseline, so the delta chip reflects "what changed vs saved".
 */
export function PreviewPanel() {
  const previewSamples = useSignalStore((s) => s.previewSamples);
  const config = useSignalStore((s) => s.config);
  const draftConfig = useSignalStore((s) => s.draftConfig);
  const hasDraft = draftConfig !== null;

  // Live region — announce "preview re-scored" each time samples change.
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    setTick((t) => t + 1);
  }, [previewSamples]);

  // Memoise baselines so we don't re-score 8× per render unnecessarily.
  const baselines = React.useMemo(
    () =>
      previewSamples.map((s) =>
        scoreMessage(s.message, config, s.country, s.postedAt).score,
      ),
    [previewSamples, config],
  );

  return (
    <aside
      className="lg:sticky lg:top-20 flex flex-col rounded-xl border bg-surface shadow-sm-signal overflow-hidden"
      aria-label="Live preview"
    >
      <header className="p-4 border-b bg-surface-sunk/40">
        <h2 className="text-sm font-semibold">Live preview</h2>
        <p className="text-xs text-text-muted mt-0.5">
          Re-scores 8 real conversations on every change
        </p>
      </header>

      <div
        className="overflow-y-auto max-h-[calc(100vh-200px)] p-3 space-y-2"
        role="region"
        aria-label="Preview conversations"
      >
        {previewSamples.length === 0 ? (
          <p className="text-sm text-text-muted p-4">No preview samples.</p>
        ) : (
          previewSamples.map((sample, i) => (
            <PreviewCard
              key={sample.id}
              sample={sample}
              baselineScore={baselines[i] ?? sample.score}
              showDelta={hasDraft}
            />
          ))
        )}
      </div>

      <div
        role="status"
        aria-live="polite"
        className="sr-only"
      >
        Preview re-scored {tick > 0 ? `(${tick})` : ""}
      </div>
    </aside>
  );
}
