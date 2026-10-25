"use client";

import * as React from "react";

/* Funnel — horizontal trapezoid bars decreasing in width.
   Demo constants as specified by the task brief.
   Each bar's trapezoid slopes from this stage's width (top edge)
   to the next stage's width (bottom edge). */

interface Stage {
  label: string;
  count: number;
}

const STAGES: Stage[] = [
  { label: "Scanned", count: 480 },
  { label: "Collected", count: 240 },
  { label: "Matched", count: 180 },
  { label: "Scored", count: 180 },
  { label: "Queued", count: 60 },
  { label: "Approved", count: 24 },
  { label: "Posted", count: 18 },
];

const BAND_COLOR = [
  "var(--text-muted)",
  "var(--text-muted)",
  "var(--info)",
  "var(--info)",
  "var(--warning)",
  "var(--primary)",
  "var(--success)",
];

const BAND_OPACITY = [0.35, 0.55, 0.7, 0.7, 0.8, 0.9, 0.95];

function pctOf(max: number, v: number): number {
  if (max <= 0) return 0;
  return Math.max(2, (v / max) * 100);
}

function dropOff(prev: number, cur: number): number {
  if (prev <= 0) return 0;
  return Math.round(((cur - prev) / prev) * 100);
}

export function Funnel() {
  const max = STAGES[0].count;
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
