"use client";

import * as React from "react";
import { Clock, Timer, Hourglass } from "lucide-react";
import { cn } from "@/lib/utils";

/* Reviewer response-time stats — three KPI-style stat cards.
   Faux values from the spec brief. */

interface Stat {
  label: string;
  value: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  tone: "primary" | "warning" | "info";
}

const STATS: Stat[] = [
  {
    label: "Avg time to first review",
    value: "4h 23m",
    description: "Across all reviewers · last 30d",
    icon: Clock,
    tone: "primary",
  },
  {
    label: "Median time",
    value: "3h 12m",
    description: "Half of items reviewed faster",
    icon: Timer,
    tone: "info",
  },
  {
    label: "P90 time",
    value: "12h 04m",
    description: "Worst-case reviewer latency",
    icon: Hourglass,
    tone: "warning",
  },
];

const TONE_CLASS: Record<Stat["tone"], string> = {
  primary: "text-primary bg-primary-soft",
  warning: "text-warning bg-warning/10",
  info: "text-info bg-info/10",
};

export function ReviewerStats() {
  return (
    <div
      role="img"
      aria-label={`Reviewer response-time stats. ${STATS.map(
        (s) => `${s.label}: ${s.value}`,
      ).join(". ")}`}
      className="grid grid-cols-1 sm:grid-cols-3 gap-3"
    >
      {STATS.map((s) => {
        const Icon = s.icon;
        return (
          <div
            key={s.label}
            className="rounded-lg border border-border bg-surface p-4 flex items-start gap-3"
          >
            <span
              className={cn(
                "rounded-md p-2 shrink-0",
                TONE_CLASS[s.tone],
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="text-xs text-text-muted truncate">{s.label}</p>
              <p className="mt-0.5 text-2xl font-semibold font-mono tabular-nums text-text">
                {s.value}
              </p>
              <p className="mt-0.5 text-[11px] text-text-muted leading-tight">
                {s.description}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
