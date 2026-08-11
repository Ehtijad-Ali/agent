"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { useSignalStore } from "@/stores/signal-store";
import type { Conversation } from "@/lib/types";
import type { Range } from "@/components/inbox/types";
import { RANGE_MS } from "@/components/inbox/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { VolumeChart, VolumeLegend } from "@/components/insights/volume-chart";
import {
  ScoreDistribution,
  ScoreBandLegend,
} from "@/components/insights/score-distribution";
import { PlatformPerformance } from "@/components/insights/platform-performance";
import { CountryHeat } from "@/components/insights/country-heat";
import { KeywordTable } from "@/components/insights/keyword-table";
import { Funnel } from "@/components/insights/funnel";
import { ReviewerStats } from "@/components/insights/reviewer-stats";

const RANGES: { id: Range; label: string }[] = [
  { id: "24h", label: "24h" },
  { id: "7d", label: "7d" },
  { id: "30d", label: "30d" },
  { id: "custom", label: "Custom" },
];

function useInRangeConvos(): {
  convos: Conversation[];
  range: Range;
  setRange: (r: Range) => void;
} {
  const conversations = useSignalStore((s) => s.conversations);
  const range = useSignalStore((s) => s.range);
  const setRange = useSignalStore((s) => s.setRange);
  const hydrate = useSignalStore((s) => s.hydrate);
  React.useEffect(() => {
    hydrate();
  }, [hydrate]);
  const inRange = React.useMemo(() => {
    const now = Date.now();
    const ms = RANGE_MS[range];
    return conversations.filter((c) => now - +new Date(c.postedAt) <= ms);
  }, [conversations, range]);
  return { convos: inRange, range, setRange };
}

function SectionCard({
  title,
  description,
  className,
  actions,
  children,
}: {
  title: string;
  description?: string;
  className?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card className={cn("py-5", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="text-sm">{title}</CardTitle>
            {description && (
              <CardDescription className="mt-0.5">{description}</CardDescription>
            )}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function InsightsView() {
  const { convos, range, setRange } = useInRangeConvos();
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Insights</h1>
          <p className="text-sm text-text-muted">
            Performance analytics across{" "}
            <span className="font-mono tabular-nums">{convos.length}</span>{" "}
            conversations in the selected range.
          </p>
        </div>
        <div
          className="inline-flex rounded-md border border-border bg-surface-sunk p-0.5"
          role="tablist"
          aria-label="Time range"
        >
          {RANGES.map((r) => (
            <button
              key={r.id}
              role="tab"
              type="button"
              aria-selected={range === r.id}
              onClick={() => setRange(r.id)}
              className={cn(
                "px-3 py-1 text-xs font-medium rounded-sm transition-colors focus-visible:outline-none",
                range === r.id
                  ? "bg-surface text-text shadow-sm-signal"
                  : "text-text-muted hover:text-text",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard
          title="Volume over time"
          description={`Discovered vs. relevant conversations, ${
            range === "24h" ? "hourly" : "daily"
          } buckets`}
          className="lg:col-span-2"
          actions={<VolumeLegend />}
        >
          <VolumeChart convos={convos} range={range} />
        </SectionCard>

        <SectionCard
          title="Score distribution"
          description="Conversations per score band"
          actions={<ScoreBandLegend />}
        >
          <ScoreDistribution convos={convos} />
        </SectionCard>

        <SectionCard
          title="Platform performance"
          description="Found · relevant · approved per platform"
        >
          <PlatformPerformance convos={convos} />
        </SectionCard>

        <SectionCard
          title="Country heat list"
          description="Top 8 countries by volume and approval rate"
        >
          <CountryHeat convos={convos} />
        </SectionCard>

        <SectionCard
          title="Conversion funnel"
          description="Pipeline drop-off from scan to post"
        >
          <Funnel />
        </SectionCard>

        <SectionCard
          title="Keyword performance"
          description="Hits, average score and approval rate per keyword. Click a header to sort."
          className="lg:col-span-2"
        >
          <KeywordTable convos={convos} />
        </SectionCard>

        <SectionCard
          title="Reviewer response time"
          description="Latency from arrival to first reviewer action"
          className="lg:col-span-2"
        >
          <ReviewerStats />
        </SectionCard>
      </div>
    </div>
  );
}
