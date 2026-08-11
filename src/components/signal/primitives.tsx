"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { Intent, RiskFlag } from "@/lib/types";
import { RISK_META } from "@/lib/constants";
import { ShieldAlert, ShieldX, ShieldMinus, ShieldCheck } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/* ============================================================
   Signal shared UI primitives — intent pill, risk pill,
   score arc, score breakdown bar, sparkline.
   No inline hex colors anywhere — tokens only.
   ============================================================ */

const INTENT_PILL_CLASS: Record<Intent, string> = {
  high: "bg-primary text-primary-foreground border-transparent",
  medium:
    "bg-transparent text-warning border-warning/40",
  low: "bg-transparent text-text-muted border-border",
  not_relevant: "bg-transparent text-text-muted border-transparent",
};

export function IntentPill({
  intent,
  score,
  className,
}: {
  intent: Intent;
  score?: number;
  className?: string;
}) {
  const label =
    intent === "high"
      ? "High intent"
      : intent === "medium"
        ? "Medium intent"
        : intent === "low"
          ? "Low intent"
          : "Not relevant";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill px-2.5 py-0.5 text-xs font-medium border",
        INTENT_PILL_CLASS[intent],
        className,
      )}
    >
      {score !== undefined && (
        <span className="font-mono tabular-nums tracking-tight">{score}</span>
      )}
      <span>{label}</span>
    </span>
  );
}

const RISK_ICON: Record<RiskFlag, React.ReactNode> = {
  underage: <ShieldAlert className="h-3.5 w-3.5" />,
  real_money: <ShieldX className="h-3.5 w-3.5" />,
  spam: <ShieldX className="h-3.5 w-3.5" />,
  negative_keyword: <ShieldMinus className="h-3.5 w-3.5" />,
  off_topic: <ShieldMinus className="h-3.5 w-3.5" />,
};

export function RiskPill({
  flag,
  className,
}: {
  flag: RiskFlag;
  className?: string;
}) {
  const meta = RISK_META[flag];
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            role="status"
            aria-label={`Risk: ${meta.label}`}
            className={cn(
              "inline-flex items-center gap-1 rounded-pill px-2.5 py-0.5 text-xs font-medium border",
              "bg-risk/10 text-risk border-risk/30",
              className,
            )}
          >
            {RISK_ICON[flag]}
            <span>{meta.label}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <p className="font-medium">{meta.label}</p>
          <p className="text-text-muted text-xs mt-0.5">{meta.description}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

const RING_COLOR_VAR: Record<Intent, string> = {
  high: "var(--primary)",
  medium: "var(--warning)",
  low: "var(--text-muted)",
  not_relevant: "var(--border)",
};

/** A thin circular progress arc around a score number. */
export function ScoreArc({
  score,
  intent,
  size = 44,
  className,
}: {
  score: number;
  intent: Intent;
  size?: number;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, score));
  const stroke = 3;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  const color = RING_COLOR_VAR[intent];
  return (
    <span
      className={cn("inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
      aria-label={`Score ${score} out of 100, ${intent}`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--border)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span
        className="absolute font-mono text-sm font-semibold tabular-nums tracking-tight"
        style={{ color: "var(--text)" }}
        aria-hidden
      >
        {score}
      </span>
    </span>
  );
}

const SEGMENT_COLORS = [
  "var(--primary)",
  "var(--info)",
  "var(--success)",
  "var(--warning)",
  "var(--risk)",
  "var(--text-muted)",
];

/** Horizontal stacked bar where each contribution is a segment. */
export function ScoreBreakdownBar({
  contributions,
  className,
  highlightRuleId,
}: {
  contributions: { ruleId: string; label: string; points: number }[];
  className?: string;
  highlightRuleId?: string;
}) {
  const pos = contributions.filter((c) => c.points > 0);
  const neg = contributions.filter((c) => c.points < 0);
  const posTotal = pos.reduce((s, c) => s + c.points, 0);
  const negTotal = Math.abs(neg.reduce((s, c) => s + c.points, 0));
  const total = posTotal + negTotal || 1;
  return (
    <div className={cn("space-y-3", className)}>
      <div
        className="flex h-2.5 w-full overflow-hidden rounded-pill bg-surface-sunk"
        role="img"
        aria-label="Score breakdown"
      >
        {contributions.map((c, i) => {
          const width = (Math.abs(c.points) / total) * 100;
          if (width === 0) return null;
          const color =
            c.points > 0
              ? SEGMENT_COLORS[i % SEGMENT_COLORS.length]
              : "var(--risk)";
          const isHighlight = highlightRuleId === c.ruleId;
          return (
            <div
              key={c.ruleId}
              className="h-full transition-all"
              style={{
                width: `${width}%`,
                background: color,
                opacity: highlightRuleId && !isHighlight ? 0.35 : 1,
              }}
              title={`${c.label}: ${c.points > 0 ? "+" : ""}${c.points}`}
            />
          );
        })}
      </div>
    </div>
  );
}

/** Mini sparkline for KPI cards. */
export function Sparkline({
  data,
  width = 80,
  height = 24,
  color = "var(--primary)",
  className,
}: {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  className?: string;
}) {
  if (data.length === 0) {
    return <div style={{ width, height }} className={cn("bg-transparent", className)} />;
  }
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const step = width / Math.max(1, data.length - 1);
  const points = data
    .map((v, i) => `${i * step},${height - ((v - min) / range) * height}`)
    .join(" ");
  return (
    <svg
      width={width}
      height={height}
      className={className}
      role="img"
      aria-label="Trend"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Delta chip — green ▲ or red ▼ with the percentage. */
export function DeltaChip({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const up = value >= 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs font-medium tabular-nums",
        up ? "text-success" : "text-risk",
        className,
      )}
      aria-label={`Change ${up ? "up" : "down"} ${Math.abs(value)} percent`}
    >
      <span aria-hidden>{up ? "▲" : "▼"}</span>
      <span>
        {up ? "+" : "−"}
        {Math.abs(value)}%
      </span>
    </span>
  );
}

/** Platform badge — glyph + label. */
export function PlatformBadge({
  platform,
  className,
  showLabel = true,
}: {
  platform: string;
  className?: string;
  showLabel?: boolean;
}) {
  const label =
    platform === "discord"
      ? "Discord"
      : platform === "telegram"
        ? "Telegram"
        : platform === "facebook"
          ? "Facebook"
          : platform === "reddit"
            ? "Reddit"
            : platform;
  const glyph =
    platform === "discord"
      ? "🎮"
      : platform === "telegram"
        ? "✈️"
        : platform === "facebook"
          ? "📘"
          : platform === "reddit"
            ? "👽"
            : "•";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-xs font-medium",
        className,
      )}
    >
      <span aria-hidden className="text-sm">
        {glyph}
      </span>
      {showLabel && <span>{label}</span>}
    </span>
  );
}

/** Country flag chip — renders emoji flag. */
export function CountryFlag({
  code,
  className,
  showLabel = false,
  name,
}: {
  code: string;
  className?: string;
  showLabel?: boolean;
  name?: string;
}) {
  const flags: Record<string, string> = {
    US: "🇺🇸",
    GB: "🇬🇧",
    CA: "🇨🇦",
    AU: "🇦🇺",
    DE: "🇩🇪",
    FR: "🇫🇷",
    BR: "🇧🇷",
    IN: "🇮🇳",
    PH: "🇵🇭",
    NG: "🇳🇬",
    ZA: "🇿🇦",
    MX: "🇲🇽",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs",
        className,
      )}
      aria-label={name ?? code}
    >
      <span aria-hidden className="text-sm leading-none">
        {flags[code] ?? "🏳️"}
      </span>
      {showLabel && <span>{name ?? code}</span>}
    </span>
  );
}

/** Skeleton block for async regions. */
export function SignalSkeleton({
  className,
  lines = 3,
}: {
  className?: string;
  lines?: number;
}) {
  return (
    <div className={cn("space-y-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-3 bg-surface-sunk rounded-sm animate-pulse"
          style={{ width: `${100 - i * 15}%` }}
        />
      ))}
    </div>
  );
}

/** Empty state — illustrated with an icon, message, and optional action. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center py-16 px-6",
        className,
      )}
    >
      <div className="rounded-md p-3 bg-primary-soft text-primary mb-4">
        <Icon className="h-6 w-6" />
      </div>
      <p className="text-base font-medium text-text">{title}</p>
      {description && (
        <p className="text-sm text-text-muted mt-1 max-w-sm">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
