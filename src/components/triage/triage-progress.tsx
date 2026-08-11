"use client";

import * as React from "react";
import { Progress } from "@/components/ui/progress";

/**
 * TriageProgress — thin progress bar at the top of the triage screen.
 * Shows "{cleared} of {total} cleared" plus the shadcn Progress indicator.
 *
 * `total` is the count of unreviewed items captured once on mount of the
 * orchestrator (see TriageView). `cleared` is the number decided this
 * session, derived as `total - currentQueueLength`.
 */
export function TriageProgress({
  cleared,
  total,
}: {
  cleared: number;
  total: number;
}) {
  const safeTotal = Math.max(1, total);
  const pct = Math.min(100, Math.round((cleared / safeTotal) * 100));
  const clampedCleared = Math.min(cleared, total);

  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 border-b bg-surface/95 backdrop-blur"
      role="status"
      aria-live="polite"
      aria-label={`${clampedCleared} of ${total} conversations cleared`}
    >
      <div className="flex items-baseline gap-1.5 text-xs shrink-0">
        <span className="font-mono font-semibold tabular-nums text-text">
          {clampedCleared}
        </span>
        <span className="text-text-muted">of</span>
        <span className="font-mono tabular-nums text-text-muted">{total}</span>
        <span className="text-text-muted">cleared</span>
      </div>
      <Progress
        value={pct}
        className="flex-1 h-1.5 bg-surface-sunk"
        aria-hidden
      />
    </div>
  );
}
