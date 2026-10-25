"use client";

import * as React from "react";
import { Clock, Timer, Hourglass } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/lib/types";

/* Reviewer response-time stats — three KPI-style stat cards, measured from
   when a conversation was discovered to the first action a person took on
   it (system and AI-agent entries do not count as review). */

interface Stat {
  label: string;
  value: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  tone: "primary" | "warning" | "info";
}

const TONE_CLASS: Record<Stat["tone"], string> = {
  primary: "text-primary bg-primary-soft",
  warning: "text-warning bg-warning/10",
  info: "text-info bg-info/10",
};

const AUTOMATED_ACTORS = new Set(["system", "AI agent"]);

function latencyMs(c: Conversation): number | null {
  const discovered =
    c.history.find((h) => h.action === "discovered by scan")?.at ?? c.postedAt;
  const reviewed = c.history.find((h) => !AUTOMATED_ACTORS.has(h.actor));
  if (!reviewed) return null;
  const ms = +new Date(reviewed.at) - +new Date(discovered);
  return Number.isFinite(ms) && ms >= 0 ? ms : null;
}

function percentile(sorted: number[], p: number): number {
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}

function formatDuration(ms: number): string {
  const minutes = Math.round(ms / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

export function ReviewerStats({ convos }: { convos: Conversation[] }) {
  const latencies = React.useMemo(
    () =>
      convos
        .map(latencyMs)
        .filter((v): v is number => v !== null)
        .sort((a, b) => a - b),
    [convos],
  );

  if (latencies.length === 0) {
    return (
      <p className="text-sm text-text-muted">
        No reviewed conversations in this range yet.
      </p>
    );
  }

  const average = latencies.reduce((sum, v) => sum + v, 0) / latencies.length;
  const stats: Stat[] = [
    {
      label: "Avg time to first review",
      value: formatDuration(average),
      description: `Across ${latencies.length} reviewed conversation${latencies.length === 1 ? "" : "s"}`,
      icon: Clock,
      tone: "primary",
    },
    {
      label: "Median time",
      value: formatDuration(percentile(latencies, 50)),
      description: "Half of items reviewed faster",
      icon: Timer,
      tone: "info",
    },
    {
      label: "P90 time",
      value: formatDuration(percentile(latencies, 90)),
      description: "Worst-case reviewer latency",
      icon: Hourglass,
      tone: "warning",
    },
  ];

  return (
    <div
      role="img"
      aria-label={`Reviewer response-time stats. ${stats
        .map((s) => `${s.label}: ${s.value}`)
        .join(". ")}`}
      className="grid grid-cols-1 sm:grid-cols-3 gap-3"
    >
      {stats.map((s) => {
        const Icon = s.icon;
        return (
          <div
            key={s.label}
            className="rounded-lg border border-border bg-surface p-4 flex items-start gap-3"
          >
            <span className={cn("rounded-md p-2 shrink-0", TONE_CLASS[s.tone])}>
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
