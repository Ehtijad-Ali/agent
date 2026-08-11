"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { Conversation, Platform } from "@/lib/types";
import { PLATFORMS } from "@/lib/constants";

/* Platform performance — for each of the 4 platforms, show three
   grouped horizontal bars: Found · Relevant · Approved.
   Rendered as custom %-based rows (cleaner than vertical BarChart
   for small N and easier to make accessible). */

interface Row {
  platform: Platform;
  found: number;
  relevant: number;
  approved: number;
}

const RELEVANT = (c: Conversation) =>
  c.intent !== "not_relevant" && c.riskFlags.length === 0;

function buildRows(convos: Conversation[]): Row[] {
  const platforms: Platform[] = ["discord", "telegram", "facebook", "reddit"];
  const rows = platforms.map((p) => ({
    platform: p,
    found: 0,
    relevant: 0,
    approved: 0,
  }));
  const idx = new Map<Platform, number>(platforms.map((p, i) => [p, i]));
  for (const c of convos) {
    const i = idx.get(c.platform);
    if (i === undefined) continue;
    rows[i].found += 1;
    if (RELEVANT(c)) rows[i].relevant += 1;
    if (c.status === "approved") rows[i].approved += 1;
  }
  return rows;
}

const BAR_META = [
  {
    key: "found" as const,
    label: "Found",
    color: "var(--text-muted)",
    opacity: 0.55,
  },
  {
    key: "relevant" as const,
    label: "Relevant",
    color: "var(--info)",
    opacity: 0.7,
  },
  {
    key: "approved" as const,
    label: "Approved",
    color: "var(--primary)",
    opacity: 0.85,
  },
];

function BarRow({ row, max }: { row: Row; max: number }) {
  const meta = PLATFORMS[row.platform];
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="inline-flex items-center gap-1.5 font-medium text-text">
          <span aria-hidden className="text-sm">
            {meta.glyph}
          </span>
          {meta.label}
        </span>
        <span className="text-text-muted font-mono tabular-nums">
          {row.found} found
        </span>
      </div>
      <div className="space-y-1">
        {BAR_META.map((m) => {
          const v = row[m.key];
          const pct = max === 0 ? 0 : (v / max) * 100;
          return (
            <div key={m.key} className="flex items-center gap-2 text-xs">
              <span className="w-16 text-text-muted shrink-0">{m.label}</span>
              <div className="relative h-3.5 flex-1 rounded-pill bg-surface-sunk overflow-hidden">
                <div
                  className="h-full rounded-pill transition-all"
                  style={{
                    width: `${Math.max(pct, v > 0 ? 2 : 0)}%`,
                    background: m.color,
                    opacity: m.opacity,
                  }}
                />
              </div>
              <span className="w-8 text-right font-mono tabular-nums text-text">
                {v}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function PlatformPerformance({ convos }: { convos: Conversation[] }) {
  const rows = React.useMemo(() => buildRows(convos), [convos]);
  const max = Math.max(1, ...rows.map((r) => r.found));
  return (
    <div
      role="img"
      aria-label={`Platform performance. ${rows
        .map(
          (r) =>
            `${PLATFORMS[r.platform].label}: ${r.found} found, ${r.relevant} relevant, ${r.approved} approved`,
        )
        .join(". ")}`}
    >
      <div className="space-y-4">
        {rows.map((r) => (
          <BarRow key={r.platform} row={r} max={max} />
        ))}
      </div>
      <div
        className={cn(
          "mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted",
        )}
      >
        {BAR_META.map((m) => (
          <span key={m.key} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-[2px]"
              style={{ background: m.color, opacity: m.opacity }}
            />
            {m.label}
          </span>
        ))}
      </div>
    </div>
  );
}
