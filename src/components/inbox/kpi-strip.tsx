"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Sparkline, DeltaChip } from "@/components/signal/primitives";
import type { KpiData, Range } from "./types";

const RANGES: { id: Range; label: string }[] = [
  { id: "24h", label: "24h" },
  { id: "7d", label: "7d" },
  { id: "30d", label: "30d" },
  { id: "custom", label: "Custom" },
];

interface KpiCardProps {
  label: string;
  value: number;
  series: number[];
  delta: number;
  active: boolean;
  onClick: () => void;
}

function KpiCard({ label, value, series, delta, active, onClick }: KpiCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "text-left rounded-xl border bg-surface p-4 transition-all hover:shadow-md-signal focus-visible:outline-none",
        active ? "border-primary ring-1 ring-primary/30" : "border-border hover:border-text-muted/40",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-text-muted truncate">{label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums font-mono text-text">
            {value}
          </p>
        </div>
        <Sparkline data={series} width={72} height={24} />
      </div>
      <div className="mt-2 flex items-center gap-1.5">
        <DeltaChip value={delta} />
        <span className="text-xs text-text-muted">vs previous</span>
      </div>
    </button>
  );
}

export function KpiStrip({
  kpis,
  range,
  onRangeChange,
  activeKpi,
  onKpiClick,
}: {
  kpis: KpiData;
  range: Range;
  onRangeChange: (r: Range) => void;
  activeKpi: string | null;
  onKpiClick: (id: string) => void;
}) {
  return (
    <section className="space-y-3" aria-label="Key performance indicators">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-text">Performance</h2>
        <div
          className="inline-flex rounded-md border bg-surface-sunk p-0.5"
          role="tablist"
          aria-label="Time range"
        >
          {RANGES.map((r) => (
            <button
              key={r.id}
              role="tab"
              type="button"
              aria-selected={range === r.id}
              onClick={() => onRangeChange(r.id)}
              className={cn(
                "px-2.5 py-1 text-xs font-medium rounded-sm transition-colors focus-visible:outline-none",
                range === r.id
                  ? "bg-surface text-text shadow-sm-signal"
                  : "text-text-muted hover:text-text",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          label="Discovered"
          value={kpis.discovered}
          series={kpis.discoveredSeries}
          delta={kpis.deltaDiscovered}
          active={activeKpi === "discovered"}
          onClick={() => onKpiClick("discovered")}
        />
        <KpiCard
          label="Relevant"
          value={kpis.relevant}
          series={kpis.relevantSeries}
          delta={kpis.deltaRelevant}
          active={activeKpi === "relevant"}
          onClick={() => onKpiClick("relevant")}
        />
        <KpiCard
          label="High intent"
          value={kpis.highIntent}
          series={kpis.highIntentSeries}
          delta={kpis.deltaHighIntent}
          active={activeKpi === "highIntent"}
          onClick={() => onKpiClick("highIntent")}
        />
        <KpiCard
          label="Awaiting review"
          value={kpis.awaitingReview}
          series={kpis.awaitingSeries}
          delta={kpis.deltaAwaitingReview}
          active={activeKpi === "awaiting"}
          onClick={() => onKpiClick("awaiting")}
        />
      </div>
    </section>
  );
}
