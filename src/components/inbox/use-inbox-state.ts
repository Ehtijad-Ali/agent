"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import { useIsMobile } from "@/hooks/use-mobile";
import { SAVED_VIEWS } from "@/lib/constants";
import type { Conversation, Status } from "@/lib/types";
import {
  type CustomView,
  type FilterState,
  RANGE_MS,
  passesFilters,
  savedViewToFilters,
} from "./types";
import {
  buildChips,
  computeKpis,
  savedViewCount,
  sortConvos,
  toggle,
  useMediaQuery,
} from "./helpers";

/**
 * Encapsulates all Inbox state + derived data + handlers so the view
 * component stays a thin render layer.
 */
export function useInboxState() {
  const conversations = useSignalStore((s) => s.conversations);
  const loading = useSignalStore((s) => s.loading);
  const range = useSignalStore((s) => s.range);
  const setRange = useSignalStore((s) => s.setRange);
  const selectedId = useSignalStore((s) => s.selectedConversationId);
  const setSelectedId = useSignalStore((s) => s.setSelectedConversationId);
  const selectedIds = useSignalStore((s) => s.selectedIds);
  const setSelectedIds = useSignalStore((s) => s.setSelectedIds);
  const sortKey = useSignalStore((s) => s.sortKey);
  const setSortKey = useSignalStore((s) => s.setSortKey);
  const savedView = useSignalStore((s) => s.savedView);
  const setSavedView = useSignalStore((s) => s.setSavedView);
  const platformFilter = useSignalStore((s) => s.platformFilter);
  const intentFilter = useSignalStore((s) => s.intentFilter);
  const countryFilter = useSignalStore((s) => s.countryFilter);
  const hasRiskFilter = useSignalStore((s) => s.hasRiskFilter);
  const scoreRange = useSignalStore((s) => s.scoreRange);
  const setPlatformFilter = useSignalStore((s) => s.setPlatformFilter);
  const setIntentFilter = useSignalStore((s) => s.setIntentFilter);
  const setCountryFilter = useSignalStore((s) => s.setCountryFilter);
  const setHasRiskFilter = useSignalStore((s) => s.setHasRiskFilter);
  const setScoreRange = useSignalStore((s) => s.setScoreRange);

  const [statusFilter, setStatusFilter] = React.useState<Status[]>([]);
  const [inspectorCollapsed, setInspectorCollapsed] = React.useState(false);
  const [customViews, setCustomViews] = React.useState<CustomView[]>([]);
  const [activeKpi, setActiveKpi] = React.useState<string | null>(null);
  const lastCheckedIndex = React.useRef<number>(-1);

  const isMobile = useIsMobile();
  const isLarge = useMediaQuery("(min-width: 1024px)");

  const filters: FilterState = React.useMemo(
    () => ({
      savedView,
      platformFilter,
      intentFilter,
      countryFilter,
      statusFilter,
      hasRiskFilter,
      scoreRange,
    }),
    [savedView, platformFilter, intentFilter, countryFilter, statusFilter, hasRiskFilter, scoreRange],
  );

  const inRange = React.useMemo(() => {
    const n = Date.now();
    const ms = RANGE_MS[range];
    return conversations.filter((c) => n - +new Date(c.postedAt) <= ms);
  }, [conversations, range]);

  const kpis = React.useMemo(
    () => computeKpis(conversations, range),
    [conversations, range],
  );

  const savedViewCounts = React.useMemo(() => {
    const counts: Record<string, number> = {};
    for (const v of SAVED_VIEWS) counts[v.id] = savedViewCount(inRange, v.id);
    return counts;
  }, [inRange]);

  const filtered = React.useMemo(
    () => sortConvos(inRange.filter((c) => passesFilters(c, filters)), sortKey),
    [inRange, filters, sortKey],
  );

  const selectedConversation = React.useMemo(
    () => conversations.find((c) => c.id === selectedId) ?? null,
    [conversations, selectedId],
  );

  const checkedSet = React.useMemo(() => new Set(selectedIds), [selectedIds]);
  const selectedConvos = React.useMemo(
    () => conversations.filter((c) => checkedSet.has(c.id)),
    [conversations, checkedSet],
  );

  const announcement = selectedConversation
    ? `Selected ${selectedConversation.community}. Score ${selectedConversation.score}, ${selectedConversation.intent} intent.`
    : "No conversation selected.";

  const clearAttributeFilters = React.useCallback(() => {
    setPlatformFilter([]);
    setIntentFilter([]);
    setCountryFilter([]);
    setHasRiskFilter(null);
    setScoreRange([0, 100]);
    setStatusFilter([]);
  }, [
    setPlatformFilter,
    setIntentFilter,
    setCountryFilter,
    setHasRiskFilter,
    setScoreRange,
  ]);

  const handleSelect = React.useCallback(
    (id: string) => {
      setSelectedId(id === "" ? null : id);
      if (id) setActiveKpi(null);
    },
    [setSelectedId],
  );

  const handleToggleCheck = React.useCallback(
    (id: string, shiftKey: boolean) => {
      const idx = filtered.findIndex((c) => c.id === id);
      if (shiftKey && lastCheckedIndex.current >= 0 && idx >= 0) {
        const lo = Math.min(lastCheckedIndex.current, idx);
        const hi = Math.max(lastCheckedIndex.current, idx);
        const rangeIds = filtered.slice(lo, hi + 1).map((c) => c.id);
        const allSelected = rangeIds.every((rid) => selectedIds.includes(rid));
        setSelectedIds(
          allSelected
            ? selectedIds.filter((rid) => !rangeIds.includes(rid))
            : Array.from(new Set([...selectedIds, ...rangeIds])),
        );
      } else {
        setSelectedIds(toggle(selectedIds, id));
      }
      lastCheckedIndex.current = idx;
    },
    [filtered, selectedIds, setSelectedIds],
  );

  const handleKpiClick = React.useCallback(
    (id: string) => {
      setActiveKpi((prev) => (prev === id ? null : id));
      if (id === "discovered") clearAttributeFilters();
      else if (id === "relevant") {
        setIntentFilter(["high", "medium", "low"]);
        setHasRiskFilter(false);
        setStatusFilter([]);
      } else if (id === "highIntent") {
        setIntentFilter(["high"]);
        setHasRiskFilter(null);
        setStatusFilter([]);
      } else if (id === "awaiting") {
        setStatusFilter(["new", "awaiting"]);
        setIntentFilter([]);
        setHasRiskFilter(null);
      }
    },
    [clearAttributeFilters, setIntentFilter, setHasRiskFilter],
  );

  const handleClearFilters = React.useCallback(() => {
    clearAttributeFilters();
    setSavedView("all");
    setActiveKpi(null);
  }, [clearAttributeFilters, setSavedView]);

  const handleSavedViewClick = React.useCallback(
    (id: string) => {
      if (id.startsWith("custom:")) {
        const cv = customViews.find((v) => v.id === id.slice(7));
        if (cv) {
          setSavedView("all");
          setPlatformFilter(cv.filters.platformFilter);
          setIntentFilter(cv.filters.intentFilter);
          setCountryFilter(cv.filters.countryFilter);
          setStatusFilter(cv.filters.statusFilter);
          setHasRiskFilter(cv.filters.hasRiskFilter);
          setScoreRange(cv.filters.scoreRange);
        }
        return;
      }
      setSavedView(id);
      clearAttributeFilters();
      const preset = savedViewToFilters(id);
      if (preset.intentFilter) setIntentFilter(preset.intentFilter);
      if (preset.hasRiskFilter !== undefined)
        setHasRiskFilter(preset.hasRiskFilter ?? null);
      if (preset.statusFilter) setStatusFilter(preset.statusFilter);
      setActiveKpi(null);
    },
    [customViews, clearAttributeFilters, setSavedView, setIntentFilter, setHasRiskFilter, setPlatformFilter, setCountryFilter, setScoreRange],
  );

  const handleRemoveChip = React.useCallback(
    (key: keyof FilterState, value?: string) => {
      if (key === "platformFilter")
        setPlatformFilter(platformFilter.filter((x) => x !== value));
      else if (key === "intentFilter")
        setIntentFilter(intentFilter.filter((x) => x !== value));
      else if (key === "countryFilter")
        setCountryFilter(countryFilter.filter((x) => x !== value));
      else if (key === "statusFilter")
        setStatusFilter(statusFilter.filter((x) => x !== value));
      else if (key === "hasRiskFilter") setHasRiskFilter(null);
      else if (key === "scoreRange") setScoreRange([0, 100]);
    },
    [platformFilter, intentFilter, countryFilter, statusFilter, setPlatformFilter, setIntentFilter, setCountryFilter, setHasRiskFilter, setScoreRange],
  );

  const handleSaveView = React.useCallback(
    (name: string) => {
      setCustomViews((prev) => [
        ...prev,
        { id: `cv_${Date.now()}`, name, filters: { ...filters } },
      ]);
    },
    [filters],
  );

  const handleAfterAction = React.useCallback(() => {
    const next = filtered.find(
      (c) =>
        c.id !== selectedId && (c.status === "new" || c.status === "awaiting"),
    );
    if (next) setSelectedId(next.id);
  }, [filtered, selectedId, setSelectedId]);

  const chips = React.useMemo(
    () => buildChips(filters, handleRemoveChip),
    [filters, handleRemoveChip],
  );

  return {
    conversations,
    loading,
    range,
    setRange,
    selectedId,
    setSelectedId,
    selectedIds,
    setSelectedIds,
    sortKey,
    setSortKey,
    savedView,
    filters,
    kpis,
    savedViewCounts,
    filtered,
    selectedConversation,
    selectedConvos,
    announcement,
    isMobile,
    isLarge,
    inspectorCollapsed,
    setInspectorCollapsed,
    customViews,
    setCustomViews,
    activeKpi,
    checkedSet,
    chips,
    platformFilter,
    intentFilter,
    countryFilter,
    setPlatformFilter,
    setIntentFilter,
    setCountryFilter,
    setScoreRange,
    setHasRiskFilter,
    handleSelect,
    handleToggleCheck,
    handleKpiClick,
    handleClearFilters,
    handleSavedViewClick,
    handleRemoveChip,
    handleSaveView,
    handleAfterAction,
  };
}

export type { Conversation };
