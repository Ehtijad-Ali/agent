"use client";

import * as React from "react";
import type { Conversation } from "@/lib/types";

/* Funnel — horizontal trapezoid bars decreasing in width, counted from the
   conversations in the selected range. Each bar's trapezoid slopes from this
   stage's width (top edge) to the next stage's width (bottom edge). */

interface Stage {
  label: string;
  count: number;
}

const APPROVED = new Set(["approved", "manually_posted", "sent"]);
const POSTED = new Set(["manually_posted", "sent"]);

function stagesFor(convos: Conversation[]): Stage[] {
  const matched = convos.filter((c) => c.matchedKeywords.length > 0);
  const relevant = convos.filter((c) => c.intent !== "not_relevant");
  const safe = relevant.filter((c) => c.riskFlags.length === 0);
  return [
    { label: "Collected", count: convos.length },
    { label: "Matched", count: matched.length },
    { label: "Relevant", count: relevant.length },
    { label: "Safe", count: safe.length },
    { label: "Approved", count: convos.filter((c) => APPROVED.has(c.status)).length },
    { label: "Posted", count: convos.filter((c) => POSTED.has(c.status)).length },
  ];
}

const BAND_COLOR = [
  "var(--text-muted)",
  "var(--info)",
  "var(--info)",
  "var(--warning)",
  "var(--primary)",
  "var(--success)",
];

const BAND_OPACITY = [0.45, 0.7, 0.7, 0.8, 0.9, 0.95];

function pctOf(max: number, v: number): number {
  if (max <= 0) return 0;
  return Math.max(2, (v / max) * 100);
}

function dropOff(prev: number, cur: number): number {
  if (prev <= 0) return 0;
  return Math.round(((cur - prev) / prev) * 100);
}

export function Funnel({ convos }: { convos: Conversation[] }) {
  const STAGES = React.useMemo(() => stagesFor(convos), [convos]);
  const max = STAGES[0].count;
  if (max === 0) {
    return <p className="text-sm text-text-muted">No conversations in this range yet.</p>;
  }
  return (
    <div
      role="img"
      aria-label={`Conversion funnel. ${STAGES.map((s, i) =>
        i === 0
          ? `${s.label} ${s.count}`
          : `${s.label} ${s.count}, drop-off ${dropOff(STAGES[i - 1].count, s.count)} percent from previous`,
      ).join(". ")}`}
    >
      <ul className="space-y-1">
        {STAGES.map((s, i) => {
          const widthPct = pctOf(max, s.count);
          const next = i < STAGES.length - 1 ? STAGES[i + 1] : null;
          const prev = i > 0 ? STAGES[i - 1] : null;
          const drop = prev === null ? null : dropOff(prev.count, s.count);
          /* trapezoid: top edge spans 0→100% of this bar,
             bottom edge spans (50 - 50r)% → (50 + 50r)% where r = next/cur */
          const r = next === null ? 1 : Math.min(1, next.count / s.count);
          const slopeRight = 50 + 50 * r;
          const slopeLeft = 50 - 50 * r;
          const clipPath =
            next === null
              ? undefined
              : `polygon(0 0, 100% 0, ${slopeRight}% 100%, ${slopeLeft}% 100%)`;
          return (
            <li key={s.label} className="space-y-0.5">
              {drop !== null && (
                <div className="flex items-center justify-center gap-1 text-[10px] text-text-muted">
                  <span aria-hidden>↓</span>
                  <span className="font-mono tabular-nums">{drop}%</span>
                  <span className="text-text-muted/70">drop-off</span>
                </div>
              )}
              <div className="flex items-center gap-3">
                <span className="w-20 shrink-0 text-xs font-medium text-text">
                  {s.label}
                </span>
                <div className="relative flex-1 h-7 flex items-center">
                  <div
                    className="absolute inset-y-0 left-1/2 -translate-x-1/2 flex items-center justify-center"
                    style={{
                      width: `${widthPct}%`,
                      background: BAND_COLOR[i],
                      opacity: BAND_OPACITY[i],
                      clipPath,
                    }}
                    aria-hidden
                  />
                  <span
                    className="absolute left-1/2 -translate-x-1/2 text-xs font-mono font-semibold tabular-nums text-text"
                    style={{ zIndex: 1 }}
                  >
                    {s.count}
                  </span>
                </div>
                <span className="w-12 shrink-0 text-right text-xs text-text-muted font-mono tabular-nums">
                  {Math.round((s.count / max) * 100)}%
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
