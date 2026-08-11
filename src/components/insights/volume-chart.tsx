"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { Conversation } from "@/lib/types";
import type { Range } from "@/components/inbox/types";
import { RANGE_MS } from "@/components/inbox/types";
import { format } from "date-fns";

/* Volume over time — stacked area chart with two series:
   "Discovered" (primary teal) and "Relevant" (info blue).
   Buckets: 24h → hourly, 7d/30d → daily. */

interface Bucket {
  label: string;
  discovered: number;
  relevant: number;
}

const RELEVANT = (c: Conversation) =>
  c.intent !== "not_relevant" && c.riskFlags.length === 0;

function buildSeries(convos: Conversation[], range: Range): Bucket[] {
  const now = Date.now();
  const rangeMs = RANGE_MS[range];
  const buckets = range === "24h" ? 24 : range === "7d" ? 7 : 30;
  const bucketMs = rangeMs / buckets;
  const fmt = range === "24h" ? "HH:mm" : range === "7d" ? "EEE" : "M/d";
  const pts: Bucket[] = Array.from({ length: buckets }, (_, i) => {
    const start = now - rangeMs + i * bucketMs;
    return { label: format(start, fmt), discovered: 0, relevant: 0 };
  });
  for (const c of convos) {
    const age = now - +new Date(c.postedAt);
    if (age < 0 || age > rangeMs) continue;
    const idx = buckets - 1 - Math.floor(age / bucketMs);
    if (idx < 0 || idx >= buckets) continue;
    pts[idx].discovered += 1;
    if (RELEVANT(c)) pts[idx].relevant += 1;
  }
  return pts;
}

interface TooltipProps {
  active?: boolean;
  payload?: { value: number; name: string; color: string }[];
  label?: string;
}

function ChartTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      className="rounded-lg border border-border/60 bg-surface px-2.5 py-1.5 text-xs shadow-md-signal"
      role="status"
    >
      <p className="font-medium text-text mb-1">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-[2px]"
            style={{ background: p.color }}
          />
          <span className="text-text-muted">{p.name}</span>
          <span className="ml-auto font-mono tabular-nums text-text">
            {p.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export function VolumeChart({
  convos,
  range,
}: {
  convos: Conversation[];
  range: Range;
}) {
  const data = React.useMemo(() => buildSeries(convos, range), [convos, range]);
  const ariaLabel = `Volume over time, ${range}. Discovered and relevant conversations per ${
    range === "24h" ? "hour" : "day"
  }.`;
  return (
    <div className="h-[260px] w-full" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <defs>
            <linearGradient id="gradDiscovered" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.55} />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="gradRelevant" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--info)" stopOpacity={0.5} />
              <stop offset="100%" stopColor="var(--info)" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--border)"
            strokeOpacity={0.4}
            vertical={false}
          />
          <XAxis
            dataKey="label"
            stroke="var(--text-muted)"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            interval={Math.max(0, Math.floor(data.length / 8) - 1)}
            minTickGap={8}
          />
          <YAxis
            stroke="var(--text-muted)"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            width={28}
            allowDecimals={false}
          />
          <Tooltip
            content={<ChartTooltip />}
            cursor={{ stroke: "var(--border)", strokeWidth: 1 }}
          />
          <Area
            type="monotone"
            dataKey="discovered"
            name="Discovered"
            stackId="1"
            stroke="var(--primary)"
            strokeWidth={2}
            fill="url(#gradDiscovered)"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="relevant"
            name="Relevant"
            stackId="1"
            stroke="var(--info)"
            strokeWidth={2}
            fill="url(#gradRelevant)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Compact legend so users see what teal / blue mean. */
export function VolumeLegend({ className }: { className?: string }) {
  return (
    <div
      className={cn("flex items-center gap-4 text-xs text-text-muted", className)}
    >
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block h-2.5 w-2.5 rounded-[2px]"
          style={{ background: "var(--primary)" }}
        />
        Discovered
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block h-2.5 w-2.5 rounded-[2px]"
          style={{ background: "var(--info)" }}
        />
        Relevant
      </span>
    </div>
  );
}
