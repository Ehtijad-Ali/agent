"use client";

import * as React from "react";
import { Filter, X } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* ============================================================
   Activity filters — actor dropdown, action search, date range,
   item-id search. State is owned by the parent view; this is a
   controlled presentational component.
   ============================================================ */

export type ActorFilter = "all" | "system" | "you";

export interface ActivityFiltersState {
  actor: ActorFilter;
  actionQuery: string;
  itemId: string;
  from: string; // YYYY-MM-DD or ""
  to: string; // YYYY-MM-DD or ""
}

export const EMPTY_FILTERS: ActivityFiltersState = {
  actor: "all",
  actionQuery: "",
  itemId: "",
  from: "",
  to: "",
};

interface ActivityFiltersProps {
  value: ActivityFiltersState;
  onChange: (next: ActivityFiltersState) => void;
}

export function ActivityFilters({ value, onChange }: ActivityFiltersProps) {
  const patch = (p: Partial<ActivityFiltersState>) =>
    onChange({ ...value, ...p });

  const clearable =
    value.actor !== "all" ||
    value.actionQuery !== "" ||
    value.itemId !== "" ||
    value.from !== "" ||
    value.to !== "";

  return (
    <div
      className={cn(
        "flex flex-wrap items-end gap-3 rounded-xl border bg-surface px-4 py-3 shadow-sm-signal",
      )}
      role="search"
      aria-label="Filter activity log"
    >
      {/* Actor */}
      <div className="space-y-1">
        <label
          htmlFor="activity-actor"
          className="block text-xs font-medium text-text-muted"
        >
          Actor
        </label>
        <Select
          value={value.actor}
          onValueChange={(v) => patch({ actor: v as ActorFilter })}
        >
          <SelectTrigger id="activity-actor" size="sm" className="w-36">
            <SelectValue placeholder="All" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="system">System</SelectItem>
            <SelectItem value="you">You</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Action search */}
      <div className="space-y-1 flex-1 min-w-[180px]">
        <label
          htmlFor="activity-action"
          className="block text-xs font-medium text-text-muted"
        >
          Action
        </label>
        <Input
          id="activity-action"
          type="search"
          placeholder="Search actions…"
          value={value.actionQuery}
          onChange={(e) => patch({ actionQuery: e.target.value })}
          className="h-8"
        />
      </div>

      {/* From */}
      <div className="space-y-1">
        <label
          htmlFor="activity-from"
          className="block text-xs font-medium text-text-muted"
        >
          From
        </label>
        <Input
          id="activity-from"
          type="date"
          value={value.from}
          onChange={(e) => patch({ from: e.target.value })}
          className="h-8 w-40"
        />
      </div>

      {/* To */}
      <div className="space-y-1">
        <label
          htmlFor="activity-to"
          className="block text-xs font-medium text-text-muted"
        >
          To
        </label>
        <Input
          id="activity-to"
          type="date"
          value={value.to}
          onChange={(e) => patch({ to: e.target.value })}
          className="h-8 w-40"
        />
      </div>

      {/* Item id */}
      <div className="space-y-1 flex-1 min-w-[160px]">
        <label
          htmlFor="activity-item"
          className="block text-xs font-medium text-text-muted"
        >
          Item ID
        </label>
        <Input
          id="activity-item"
          type="search"
          placeholder="conv_… / kw_… / etc."
          value={value.itemId}
          onChange={(e) => patch({ itemId: e.target.value })}
          className="h-8 font-mono text-xs"
        />
      </div>

      {clearable && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange({ ...EMPTY_FILTERS })}
          aria-label="Clear all filters"
        >
          <X className="h-3.5 w-3.5" />
          Clear
        </Button>
      )}
      <span
        className="inline-flex items-center gap-1 text-xs text-text-muted ml-auto pb-1.5"
        aria-hidden
      >
        <Filter className="h-3.5 w-3.5" />
        Filters
      </span>
    </div>
  );
}
