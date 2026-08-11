"use client";

import * as React from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { PLATFORMS } from "@/lib/constants";
import type { Conversation, Platform } from "@/lib/types";
import { cn } from "@/lib/utils";

/* ============================================================
   Live usage meter — guardrail #8.
   Shows today's approved replies vs the daily ceiling, plus a
   per-platform "last hour" bar against the per-platform-per-hour
   cap from config.rateCaps.
   ============================================================ */

const PLATFORM_ORDER: Platform[] = ["discord", "telegram", "facebook", "reddit"];

const APPROVE_ACTIONS = new Set([
  "Status changed to approved",
  "Status changed to manually_posted",
]);

/** Find the timestamp at which a conversation was approved.
 *  Falls back to postedAt for any approved seed row that has no
 *  explicit status-change history entry. */
function approvedAt(c: Conversation): number {
  for (let i = c.history.length - 1; i >= 0; i--) {
    const h = c.history[i];
    if (APPROVE_ACTIONS.has(h.action)) {
      return +new Date(h.at);
    }
  }
  return +new Date(c.postedAt);
}

interface UsageMeterProps {
  conversations: Conversation[];
  dailyCeiling: number;
  perPlatformPerHour: number;
}

export function UsageMeter({
  conversations,
  dailyCeiling,
  perPlatformPerHour,
}: UsageMeterProps) {
  const now = React.useMemo(() => Date.now(), []);

  const approved = React.useMemo(
    () =>
      conversations.filter(
        (c) => c.status === "approved" || c.status === "manually_posted",
      ),
    [conversations],
  );

  const approvedToday = React.useMemo(() => {
    const startOfDay = new Date(now);
    startOfDay.setHours(0, 0, 0, 0);
    const start = +startOfDay;
    return approved.filter((c) => approvedAt(c) >= start).length;
  }, [approved, now]);

  const perPlatformLastHour = React.useMemo(() => {
    const hourAgo = now - 60 * 60 * 1000;
    const counts: Record<Platform, number> = {
      discord: 0,
      telegram: 0,
      facebook: 0,
      reddit: 0,
    };
    for (const c of approved) {
      if (approvedAt(c) >= hourAgo) {
        counts[c.platform] = (counts[c.platform] ?? 0) + 1;
      }
    }
    return counts;
  }, [approved, now]);

  const todayPct =
    dailyCeiling > 0 ? Math.min(100, (approvedToday / dailyCeiling) * 100) : 0;
  const todayTone =
    approvedToday >= dailyCeiling
      ? "text-risk"
      : approvedToday >= dailyCeiling * 0.8
        ? "text-warning"
        : "text-text";

  return (
    <Card id="usage-meter" className="scroll-mt-24 py-5">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Live usage</CardTitle>
        <CardDescription>
          Per-platform rate caps and a daily approved-reply ceiling.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Today — daily ceiling */}
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs font-medium text-text-muted">
              Today — approved replies
            </span>
            <span className="font-mono tabular-nums text-sm">
              <span className={cn(todayTone, "font-semibold")}>
                {approvedToday}
              </span>
              <span className="text-text-muted"> / {dailyCeiling}</span>
            </span>
          </div>
          <Progress
            value={todayPct}
            aria-label={`${approvedToday} of ${dailyCeiling} approved replies today`}
            aria-valuetext={`${approvedToday} of ${dailyCeiling}`}
          />
          <p className="text-xs text-text-muted">
            Daily ceiling: <span className="font-mono">{dailyCeiling}</span>{" "}
            approved replies across all platforms.
          </p>
        </div>

        {/* Per-platform last hour */}
        <div className="space-y-2.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs font-medium text-text-muted">
              Per platform — last hour
            </span>
            <span className="text-xs text-text-muted">
              cap: <span className="font-mono">{perPlatformPerHour}</span> / hr
            </span>
          </div>
          <ul className="space-y-2" aria-label="Per-platform last-hour usage">
            {PLATFORM_ORDER.map((p) => (
              <PlatformHourBar
                key={p}
                platform={p}
                count={perPlatformLastHour[p] ?? 0}
                cap={perPlatformPerHour}
              />
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function PlatformHourBar({
  platform,
  count,
  cap,
}: {
  platform: Platform;
  count: number;
  cap: number;
}) {
  const meta = PLATFORMS[platform];
  const pct = cap > 0 ? Math.min(100, (count / cap) * 100) : 0;
  const over = count >= cap && cap > 0;
  const near = count >= cap * 0.8 && cap > 0 && !over;
  const barColor = over
    ? "var(--risk)"
    : near
      ? "var(--warning)"
      : "var(--primary)";
  return (
    <li className="flex items-center gap-3">
      <span className="w-24 inline-flex items-center gap-1.5 text-xs">
        <span aria-hidden className="text-sm leading-none">
          {meta.glyph}
        </span>
        <span className="text-text">{meta.label}</span>
      </span>
      <div
        className="relative flex-1 h-2.5 rounded-pill bg-surface-sunk overflow-hidden"
        role="meter"
        aria-valuenow={count}
        aria-valuemin={0}
        aria-valuemax={cap}
        aria-label={`${meta.label}: ${count} of ${cap} approved in the last hour`}
      >
        <div
          className="absolute inset-y-0 left-0 transition-all"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
      <span
        className={cn(
          "font-mono tabular-nums text-xs w-14 text-right",
          over ? "text-risk" : near ? "text-warning" : "text-text-muted",
        )}
      >
        {count}/{cap}
      </span>
    </li>
  );
}
