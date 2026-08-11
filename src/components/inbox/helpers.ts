"use client";

import * as React from "react";
import { PLATFORMS, COUNTRIES } from "@/lib/constants";
import type { Conversation } from "@/lib/types";
import type {
  FilterChip,
  FilterState,
  KpiData,
  Range,
  SortKey,
} from "./types";
import { RANGE_MS } from "./types";

/* ---------------- hooks ---------------- */

/** Subscribe to a CSS media query. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = React.useState(false);
  React.useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

/* ---------------- sorting ---------------- */

const INTENT_ORDER: Record<string, number> = {
  high: 0,
  medium: 1,
  low: 2,
  not_relevant: 3,
};

export function sortConvos(list: Conversation[], key: SortKey): Conversation[] {
  const arr = [...list];
  if (key === "relevance") arr.sort((a, b) => b.score - a.score);
  else if (key === "recency")
    arr.sort((a, b) => +new Date(b.postedAt) - +new Date(a.postedAt));
  else if (key === "intent")
    arr.sort(
      (a, b) => (INTENT_ORDER[a.intent] ?? 9) - (INTENT_ORDER[b.intent] ?? 9),
    );
  else if (key === "platform")
    arr.sort((a, b) => a.platform.localeCompare(b.platform));
  return arr;
}

/* ---------------- KPI computation ---------------- */

export function computeKpis(convos: Conversation[], range: Range): KpiData {
  const now = Date.now();
  const rangeMs = RANGE_MS[range];
  const inRange = convos.filter((c) => now - +new Date(c.postedAt) <= rangeMs);
  const buckets = range === "24h" ? 24 : range === "7d" ? 7 : 12;
  const bucketMs = rangeMs / buckets;
  const series = (pred: (c: Conversation) => boolean) => {
    const pts = new Array(buckets).fill(0);
    for (const c of inRange) {
      if (!pred(c)) continue;
      const age = now - +new Date(c.postedAt);
      const idx = buckets - 1 - Math.floor(age / bucketMs);
      if (idx >= 0 && idx < buckets) pts[idx]++;
    }
    return pts;
  };
  const s1 = series(() => true);
  const s2 = series(
    (c) => c.intent !== "not_relevant" && c.riskFlags.length === 0,
  );
  const s3 = series((c) => c.intent === "high");
  const s4 = series((c) => c.status === "new" || c.status === "awaiting");
  const delta = (s: number[]) => {
    const a = s[s.length - 2] ?? 0;
    const b = s[s.length - 1] ?? 0;
    if (a === 0) return b > 0 ? 100 : 0;
    return Math.round(((b - a) / a) * 100);
  };
  const sum = (s: number[]) => s.reduce((n, v) => n + v, 0);
  return {
    discovered: inRange.length,
    relevant: sum(s2),
    highIntent: sum(s3),
    awaitingReview: sum(s4),
    discoveredSeries: s1,
    relevantSeries: s2,
    highIntentSeries: s3,
    awaitingSeries: s4,
    deltaDiscovered: delta(s1),
    deltaRelevant: delta(s2),
    deltaHighIntent: delta(s3),
    deltaAwaitingReview: delta(s4),
  };
}

/* ---------------- saved view counts ---------------- */

export function savedViewCount(
  convos: Conversation[],
  viewId: string,
): number {
  switch (viewId) {
    case "all":
      return convos.length;
    case "needs_review":
      return convos.filter((c) => c.status === "new" || c.status === "awaiting")
        .length;
    case "high_intent":
      return convos.filter((c) => c.intent === "high").length;
    case "risk_flagged":
      return convos.filter((c) => c.riskFlags.length > 0).length;
    case "approved":
      return convos.filter((c) => c.status === "approved").length;
    case "rejected":
      return convos.filter((c) => c.status === "rejected").length;
    case "snoozed":
      return convos.filter((c) => c.status === "snoozed").length;
    default:
      return 0;
  }
}

/* ---------------- array util ---------------- */

export function toggle(arr: string[], id: string): string[] {
  return arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id];
}

/* ---------------- filter chips ---------------- */

export function buildChips(
  filters: FilterState,
  onRemove: (key: keyof FilterState, value?: string) => void,
): FilterChip[] {
  const chips: FilterChip[] = [];
  for (const p of filters.platformFilter) {
    const meta = PLATFORMS[p as keyof typeof PLATFORMS];
    chips.push({
      id: `platform:${p}`,
      label: meta?.label ?? p,
      onRemove: () => onRemove("platformFilter", p),
    });
  }
  for (const i of filters.intentFilter) {
    chips.push({
      id: `intent:${i}`,
      label: i.replace("_", " "),
      onRemove: () => onRemove("intentFilter", i),
    });
  }
  for (const code of filters.countryFilter) {
    const c = COUNTRIES.find((x) => x.code === code);
    chips.push({
      id: `country:${code}`,
      label: `${c?.flag ?? ""} ${c?.name ?? code}`,
      onRemove: () => onRemove("countryFilter", code),
    });
  }
  for (const s of filters.statusFilter) {
    chips.push({
      id: `status:${s}`,
      label: s.replace("_", " "),
      onRemove: () => onRemove("statusFilter", s),
    });
  }
  if (filters.hasRiskFilter !== null) {
    chips.push({
      id: "risk",
      label: filters.hasRiskFilter ? "Has risk" : "No risk",
      onRemove: () => onRemove("hasRiskFilter"),
    });
  }
  if (filters.scoreRange[0] !== 0 || filters.scoreRange[1] !== 100) {
    chips.push({
      id: "score",
      label: `Score ${filters.scoreRange[0]}–${filters.scoreRange[1]}`,
      onRemove: () => onRemove("scoreRange"),
    });
  }
  return chips;
}
