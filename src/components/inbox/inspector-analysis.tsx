"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import {
  IntentPill,
  ScoreBreakdownBar,
} from "@/components/signal/primitives";
import { PLATFORMS } from "@/lib/constants";
import { confidenceExplanation } from "@/lib/scoring";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/lib/types";

const SEGMENT_COLORS = [
  "var(--primary)",
  "var(--info)",
  "var(--success)",
  "var(--warning)",
  "var(--risk)",
  "var(--text-muted)",
];

function segmentColor(i: number, points: number) {
  return points > 0 ? SEGMENT_COLORS[i % SEGMENT_COLORS.length] : "var(--risk)";
}

const CONFIDENCE_LABEL = {
  low: "Low confidence",
  medium: "Medium confidence",
  high: "High confidence",
} as const;

const CONFIDENCE_TONE = {
  low: "text-text-muted",
  medium: "text-warning",
  high: "text-success",
} as const;

export function InspectorAnalysis({ c }: { c: Conversation }) {
  const [highlightRuleId, setHighlightRuleId] = React.useState<string | undefined>();
  const platformMeta = PLATFORMS[c.platform];

  return (
    <div className="space-y-5 px-4 py-4 overflow-y-auto">
      {/* Message */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Message
        </p>
        <blockquote
          className="border-l-2 border-primary/40 pl-3 pr-2 py-2 italic text-sm text-text bg-surface-sunk/40 rounded-r-md"
        >
          {c.message}
        </blockquote>
      </div>

      {/* Source path */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Source
        </p>
        <p className="text-sm font-mono text-text">
          <span aria-hidden>{platformMeta?.glyph}</span>{" "}
          <span>{c.platform}</span>
          <span className="text-text-muted"> / </span>
          <span>{c.community}</span>
        </p>
        <p className="text-xs text-text-muted">
          Author:{" "}
          <span className="font-mono text-text">{c.authorPseudonym}</span>
        </p>
      </div>

      {/* Intent + keywords */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Intent
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          <IntentPill intent={c.intent} score={c.score} />
          {c.matchedKeywords.map((kw) => (
            <Badge
              key={kw}
              variant="outline"
              className="bg-primary-soft text-primary border-transparent font-mono"
            >
              {kw}
            </Badge>
          ))}
          {c.matchedKeywords.length === 0 && (
            <span className="text-xs text-text-muted">No keywords matched</span>
          )}
        </div>
      </div>

      {/* AI summary */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          AI summary
        </p>
        <p className="text-sm text-text leading-relaxed">{c.summary}</p>
      </div>

      {/* Score breakdown */}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Score breakdown
          </p>
          <span className="font-mono text-sm font-semibold tabular-nums">
            {c.score}
          </span>
        </div>
        <ScoreBreakdownBar
          contributions={c.contributions}
          highlightRuleId={highlightRuleId}
        />
        <ul className="space-y-1 max-h-56 overflow-y-auto pr-1">
          {c.contributions.map((con, i) => (
            <li
              key={con.ruleId}
              onMouseEnter={() => setHighlightRuleId(con.ruleId)}
              onMouseLeave={() => setHighlightRuleId(undefined)}
              className={cn(
                "flex items-center gap-2 rounded-sm px-1.5 py-1 text-xs transition-colors cursor-default",
                highlightRuleId === con.ruleId
                  ? "bg-surface-sunk"
                  : "hover:bg-surface-sunk/60",
              )}
            >
              <span
                aria-hidden
                className="h-2.5 w-2.5 rounded-sm shrink-0"
                style={{ background: segmentColor(i, con.points) }}
              />
              <span className="flex-1 text-text truncate">{con.label}</span>
              <span
                className={cn(
                  "font-mono tabular-nums font-semibold",
                  con.points > 0 ? "text-success" : "text-risk",
                )}
              >
                {con.points > 0 ? "+" : ""}
                {con.points}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Confidence meter */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Confidence
        </p>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 rounded-full bg-surface-sunk overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width:
                  c.confidence === "high"
                    ? "100%"
                    : c.confidence === "medium"
                      ? "60%"
                      : "25%",
                background:
                  c.confidence === "high"
                    ? "var(--success)"
                    : c.confidence === "medium"
                      ? "var(--warning)"
                      : "var(--text-muted)",
              }}
            />
          </div>
          <span
            className={cn(
              "text-xs font-medium",
              CONFIDENCE_TONE[c.confidence],
            )}
          >
            {CONFIDENCE_LABEL[c.confidence]}
          </span>
        </div>
        <p className="text-xs text-text-muted leading-relaxed">
          {confidenceExplanation(c.confidence, c.contributions)}
        </p>
      </div>
    </div>
  );
}
