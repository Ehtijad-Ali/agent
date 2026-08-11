import type { Conversation, Status } from "@/lib/types";

export type Range = "24h" | "7d" | "30d" | "custom";

export type SortKey = "relevance" | "recency" | "intent" | "platform";

export interface KpiData {
  discovered: number;
  relevant: number;
  highIntent: number;
  awaitingReview: number;
  discoveredSeries: number[];
  relevantSeries: number[];
  highIntentSeries: number[];
  awaitingSeries: number[];
  deltaDiscovered: number;
  deltaRelevant: number;
  deltaHighIntent: number;
  deltaAwaitingReview: number;
}

export interface FilterState {
  savedView: string;
  platformFilter: string[];
  intentFilter: string[];
  countryFilter: string[];
  statusFilter: Status[];
  hasRiskFilter: boolean | null;
  scoreRange: [number, number];
}

export interface SavedViewMeta {
  id: string;
  label: string;
  count: number;
}

export interface FilterChip {
  id: string;
  label: string;
  onRemove: () => void;
}

export interface CustomView {
  id: string;
  name: string;
  filters: FilterState;
}

/** Range in ms for each time window. */
export const RANGE_MS: Record<Range, number> = {
  "24h": 86_400_000,
  "7d": 7 * 86_400_000,
  "30d": 30 * 86_400_000,
  custom: 30 * 86_400_000,
};

export const EMPTY_FILTERS: FilterState = {
  savedView: "all",
  platformFilter: [],
  intentFilter: [],
  countryFilter: [],
  statusFilter: [],
  hasRiskFilter: null,
  scoreRange: [0, 100],
};

/** Apply a saved-view preset to a filter state. */
export function savedViewToFilters(viewId: string): Partial<FilterState> {
  switch (viewId) {
    case "needs_review":
      return { statusFilter: ["new", "awaiting"] };
    case "high_intent":
      return { intentFilter: ["high"] };
    case "risk_flagged":
      return { hasRiskFilter: true };
    case "approved":
      return { statusFilter: ["approved"] };
    case "rejected":
      return { statusFilter: ["rejected"] };
    case "snoozed":
      return { statusFilter: ["snoozed"] };
    default:
      return {};
  }
}

/** Check whether a conversation passes the active filter set. */
export function passesFilters(c: Conversation, f: FilterState): boolean {
  if (f.platformFilter.length && !f.platformFilter.includes(c.platform)) return false;
  if (f.intentFilter.length && !f.intentFilter.includes(c.intent)) return false;
  if (f.countryFilter.length && !f.countryFilter.includes(c.country)) return false;
  if (f.statusFilter.length && !f.statusFilter.includes(c.status)) return false;
  if (f.hasRiskFilter === true && c.riskFlags.length === 0) return false;
  if (f.hasRiskFilter === false && c.riskFlags.length > 0) return false;
  if (c.score < f.scoreRange[0] || c.score > f.scoreRange[1]) return false;
  return true;
}
