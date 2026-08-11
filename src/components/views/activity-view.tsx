"use client";

import * as React from "react";
import { Download } from "lucide-react";
import { useSignalStore } from "@/stores/signal-store";
import { Button } from "@/components/ui/button";
import {
  ActivityFilters,
  EMPTY_FILTERS,
  type ActivityFiltersState,
} from "@/components/activity/activity-filters";
import { ActivityTable } from "@/components/activity/activity-table";
import { exportActivityCsv } from "@/components/activity/export-csv";
import type { ActivityEntry } from "@/lib/types";

/* ============================================================
   Activity view — filterable audit log.
   Filters bar · export-CSV button · audit-log table.
   ============================================================ */

function toDayKey(iso: string): string {
  // Returns YYYY-MM-DD for the local date of the timestamp.
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function applyFilters(
  rows: ActivityEntry[],
  f: ActivityFiltersState,
): ActivityEntry[] {
  const actionQ = f.actionQuery.trim().toLowerCase();
  const itemQ = f.itemId.trim().toLowerCase();
  return rows.filter((r) => {
    if (f.actor !== "all" && r.actor !== f.actor) return false;
    if (actionQ && !r.action.toLowerCase().includes(actionQ)) return false;
    if (itemQ && !r.item.toLowerCase().includes(itemQ)) return false;
    if (f.from) {
      const dayKey = toDayKey(r.timestamp);
      if (dayKey < f.from) return false;
    }
    if (f.to) {
      const dayKey = toDayKey(r.timestamp);
      if (dayKey > f.to) return false;
    }
    return true;
  });
}

export function ActivityView() {
  const activity = useSignalStore((s) => s.activity);
  const hydrate = useSignalStore((s) => s.hydrate);
  const [filters, setFilters] = React.useState<ActivityFiltersState>(EMPTY_FILTERS);

  React.useEffect(() => {
    hydrate();
  }, [hydrate]);

  const filtered = React.useMemo(
    () => applyFilters(activity, filters),
    [activity, filters],
  );

  const handleExport = React.useCallback(() => {
    exportActivityCsv(filtered);
  }, [filtered]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Activity</h1>
          <p className="text-sm text-text-muted">
            Every action taken in Signal, newest first.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleExport}
          disabled={filtered.length === 0}
          aria-label="Export filtered activity to CSV"
        >
          <Download className="h-3.5 w-3.5" />
          Export CSV
        </Button>
      </header>

      <ActivityFilters value={filters} onChange={setFilters} />

      <ActivityTable rows={filtered} />
    </div>
  );
}
