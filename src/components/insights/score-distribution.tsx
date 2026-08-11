"use client";

import * as React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { Conversation } from "@/lib/types";

/* Score distribution — 10 histogram buckets (0-9, 10-19, …, 90-100).
   Bars are colored by threshold band:
     0–39  not relevant  → light grey
     40–59  low          → muted
     60–79  medium       → amber tint
     80–100 high         → teal tint
*/

interface Bucket {
  label: string;
  count: number;
  band: "not_relevant" | "low" | "medium" | "high";
}

const BUCKETS = [
  { label: "0–9", lo: 0, hi: 9, band: "not_relevant" as const },
  { label: "10–19", lo: 10, hi: 19, band: "not_relevant" as const },
  { label: "20–29", lo: 20, hi: 29, band: "not_relevant" as const },
  { label: "30–39", lo: 30, hi: 39, band: "not_relevant" as const },
  { label: "40–49", lo: 40, hi: 49, band: "low" as const },
  { label: "50–59", lo: 50, hi: 59, band: "low" as const },
  { label: "60–69", lo: 60, hi: 69, band: "medium" as const },
  { label: "70–79", lo: 70, hi: 79, band: "medium" as const },
  { label: "80–89", lo: 80, hi: 89, band: "high" as const },
  { label: "90–100", lo: 90, hi: 100, band: "high" as const },
];

const BAND_STYLE: Record<
  Bucket["band"],
  { fill: string; fillOpacity: number }
> = {
  not_relevant: { fill: "var(--text-muted)", fillOpacity: 0.22 },
  low: { fill: "var(--text-muted)", fillOpacity: 0.5 },
  medium: { fill: "var(--warning)", fillOpacity: 0.6 },
  high: { fill: "var(--primary)", fillOpacity: 0.78 },
};

function buildBuckets(convos: Conversation[]): Bucket[] {
  const counts = BUCKETS.map((b) => ({
    label: b.label,
    count: 0,
    band: b.band,
  }));
  for (const c of convos) {
    const s = Math.max(0, Math.min(100, c.score));
    const idx = BUCKETS.findIndex((b) => s >= b.lo && s <= b.hi);
    if (idx >= 0) counts[idx].count += 1;
  }
  return counts;
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: Bucket; value: number }[];
}

function ChartTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const item = payload[0];
  return (
    <div
      className="rounded-lg border border-border/60 bg-surface px-2.5 py-1.5 text-xs shadow-md-signal"
      role="status"
    >
      <p className="font-medium text-text">
        Score {item.payload.label}:{" "}
        <span className="font-mono tabular-nums">{item.value}</span>
      </p>
      <p className="text-text-muted capitalize">
        {item.payload.band.replace("_", " ")}
      </p>
    </div>
  );
}

export function ScoreDistribution({ convos }: { convos: Conversation[] }) {
  const data = React.useMemo(() => buildBuckets(convos), [convos]);
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div
      className="h-[260px] w-full"
      role="img"
      aria-label={`Score distribution histogram. ${data
        .map((d) => `${d.label}: ${d.count}`)
        .join(", ")}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--border)"
            strokeOpacity={0.4}
            vertical={false}
          />
          <XAxis
            dataKey="label"
            stroke="var(--text-muted)"
            fontSize={10}
            tickLine={false}
            axisLine={false}
            interval={0}
            angle={-30}
            textAnchor="end"
            height={42}
          />
          <YAxis
            stroke="var(--text-muted)"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            width={28}
            allowDecimals={false}
            domain={[0, Math.ceil(max * 1.15)]}
          />
          <Tooltip
            content={<ChartTooltip />}
            cursor={{ fill: "var(--surface-sunk)", opacity: 0.5 }}
          />
          <Bar dataKey="count" isAnimationActive={false} radius={[3, 3, 0, 0]}>
            {data.map((b) => {
              const style = BAND_STYLE[b.band];
              return (
                <Cell
                  key={b.label}
                  fill={style.fill}
                  fillOpacity={style.fillOpacity}
                />
              );
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Compact band legend. */
export function ScoreBandLegend() {
  const items = [
    { band: "Not relevant", color: "var(--text-muted)", opacity: 0.22 },
    { band: "Low", color: "var(--text-muted)", opacity: 0.5 },
    { band: "Medium", color: "var(--warning)", opacity: 0.6 },
    { band: "High", color: "var(--primary)", opacity: 0.78 },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
      {items.map((it) => (
        <span key={it.band} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2.5 w-2.5 rounded-[2px]"
            style={{ background: it.color, opacity: it.opacity }}
          />
          {it.band}
        </span>
      ))}
    </div>
  );
}
