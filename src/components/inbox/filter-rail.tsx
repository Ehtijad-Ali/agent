"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { COUNTRIES, PLATFORMS, SAVED_VIEWS } from "@/lib/constants";
import { Check, ChevronDown, X } from "lucide-react";
import type { CustomView, FilterState } from "./types";
import { SaveViewButton } from "./save-view-button";

const INTENTS = [
  { id: "high", label: "High intent" },
  { id: "medium", label: "Medium intent" },
  { id: "low", label: "Low intent" },
  { id: "not_relevant", label: "Not relevant" },
] as const;

function toggleArray(arr: string[], id: string): string[] {
  return arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id];
}

function FilterSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
        {title}
      </p>
      {children}
    </div>
  );
}

export function FilterRail({
  filters,
  savedView,
  savedViewCounts,
  customViews,
  onSavedViewClick,
  onPlatformToggle,
  onIntentToggle,
  onCountryToggle,
  onScoreRangeChange,
  onRiskToggle,
  onSaveView,
  onDeleteCustomView,
}: {
  filters: FilterState;
  savedView: string;
  savedViewCounts: Record<string, number>;
  customViews: CustomView[];
  onSavedViewClick: (id: string) => void;
  onPlatformToggle: (id: string) => void;
  onIntentToggle: (id: string) => void;
  onCountryToggle: (id: string) => void;
  onScoreRangeChange: (v: [number, number]) => void;
  onRiskToggle: (v: boolean | null) => void;
  onSaveView: (name: string) => void;
  onDeleteCustomView: (id: string) => void;
}) {
  const countryLabel =
    filters.countryFilter.length === 0
      ? "All countries"
      : `${filters.countryFilter.length} selected`;

  const activeFiltersCount =
    filters.platformFilter.length +
    filters.intentFilter.length +
    filters.countryFilter.length +
    filters.statusFilter.length +
    (filters.hasRiskFilter !== null ? 1 : 0) +
    (filters.scoreRange[0] !== 0 || filters.scoreRange[1] !== 100 ? 1 : 0);

  return (
    <aside
      className="w-60 shrink-0 border-r bg-surface flex flex-col"
      aria-label="Filters"
    >
      <div className="p-4 border-b">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Views</h2>
          {activeFiltersCount > 0 && (
            <Badge variant="secondary" className="font-mono text-[10px]">
              {activeFiltersCount} active
            </Badge>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-5 max-h-full">
        {/* Saved views */}
        <nav className="space-y-0.5" aria-label="Saved views">
          {SAVED_VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => onSavedViewClick(v.id)}
              aria-current={savedView === v.id ? "page" : undefined}
              className={cn(
                "w-full flex items-center justify-between rounded-md px-2.5 py-1.5 text-sm transition-colors",
                savedView === v.id
                  ? "bg-primary-soft text-primary font-medium"
                  : "text-text-muted hover:bg-surface-sunk hover:text-text",
              )}
            >
              <span className="truncate">{v.label}</span>
              <span className="font-mono text-xs tabular-nums opacity-80">
                {savedViewCounts[v.id] ?? 0}
              </span>
            </button>
          ))}
        </nav>

        {/* Custom saved views */}
        {customViews.length > 0 && (
          <FilterSection title="Saved">
            <div className="space-y-0.5">
              {customViews.map((cv) => (
                <div
                  key={cv.id}
                  className="group flex items-center justify-between rounded-md px-2.5 py-1.5 text-sm hover:bg-surface-sunk"
                >
                  <button
                    type="button"
                    onClick={() => onSavedViewClick(`custom:${cv.id}`)}
                    className="flex-1 text-left text-text-muted truncate hover:text-text"
                  >
                    {cv.name}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteCustomView(cv.id)}
                    aria-label={`Delete saved view ${cv.name}`}
                    className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-risk"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </FilterSection>
        )}

        {/* Platform */}
        <FilterSection title="Platform">
          <div className="space-y-1.5">
            {Object.entries(PLATFORMS).map(([id, meta]) => (
              <Label
                key={id}
                className="flex items-center gap-2 text-sm font-normal cursor-pointer"
              >
                <Checkbox
                  checked={filters.platformFilter.includes(id)}
                  onCheckedChange={() => onPlatformToggle(id)}
                />
                <span aria-hidden className="text-sm">
                  {meta.glyph}
                </span>
                <span className="text-text">{meta.label}</span>
              </Label>
            ))}
          </div>
        </FilterSection>

        {/* Intent */}
        <FilterSection title="Intent">
          <div className="space-y-1.5">
            {INTENTS.map((i) => (
              <Label
                key={i.id}
                className="flex items-center gap-2 text-sm font-normal cursor-pointer"
              >
                <Checkbox
                  checked={filters.intentFilter.includes(i.id)}
                  onCheckedChange={() => onIntentToggle(i.id)}
                />
                <span className="text-text">{i.label}</span>
              </Label>
            ))}
          </div>
        </FilterSection>

        {/* Country */}
        <FilterSection title="Country">
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-between"
              >
                <span className="truncate">{countryLabel}</span>
                <ChevronDown className="h-3.5 w-3.5 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-1" align="start">
              <div className="max-h-72 overflow-y-auto py-1">
                {COUNTRIES.map((c) => (
                  <Label
                    key={c.code}
                    className="flex items-center gap-2 px-2 py-1.5 text-sm font-normal cursor-pointer rounded-sm hover:bg-surface-sunk"
                  >
                    <Checkbox
                      checked={filters.countryFilter.includes(c.code)}
                      onCheckedChange={() => onCountryToggle(c.code)}
                    />
                    <span aria-hidden>{c.flag}</span>
                    <span className="text-text truncate">{c.name}</span>
                  </Label>
                ))}
              </div>
            </PopoverContent>
          </Popover>
        </FilterSection>

        {/* Score range */}
        <FilterSection title={`Score range · ${filters.scoreRange[0]}–${filters.scoreRange[1]}`}>
          <div className="px-1 pt-2">
            <Slider
              min={0}
              max={100}
              step={5}
              value={filters.scoreRange}
              onValueChange={(v) => onScoreRangeChange([v[0], v[1]] as [number, number])}
            />
          </div>
        </FilterSection>

        {/* Risk flag */}
        <FilterSection title="Risk flag">
          <div className="flex items-center justify-between">
            <Label htmlFor="risk-toggle" className="text-sm font-normal cursor-pointer text-text">
              Has risk flag
            </Label>
            <Switch
              id="risk-toggle"
              checked={filters.hasRiskFilter === true}
              onCheckedChange={(checked) =>
                onRiskToggle(checked ? true : null)
              }
            />
          </div>
        </FilterSection>
      </div>

      {/* Save this view */}
      <SaveViewButton onSave={onSaveView} />
    </aside>
  );
}
