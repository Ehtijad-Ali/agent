"use client";

import * as React from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { KpiStrip } from "@/components/inbox/kpi-strip";
import { FilterRail } from "@/components/inbox/filter-rail";
import { ConversationList } from "@/components/inbox/conversation-list";
import { Inspector } from "@/components/inbox/inspector";
import { BulkActionBar } from "@/components/inbox/bulk-action-bar";
import { toggle } from "@/components/inbox/helpers";
import { useInboxState } from "@/components/inbox/use-inbox-state";

/**
 * Inbox view — home/triage surface. Three zones (filter rail · list ·
 * inspector) with a KPI strip on top and a floating bulk-action bar.
 * All state + handlers live in useInboxState; this component is the
 * thin render layer.
 */
export function InboxView() {
  const s = useInboxState();

  const inspectorEl = (
    <Inspector
      conversation={s.selectedConversation}
      collapsed={s.inspectorCollapsed}
      onToggleCollapse={() => s.setInspectorCollapsed((c) => !c)}
      onAfterAction={s.handleAfterAction}
    />
  );

  const filterRailEl = (
    <FilterRail
      filters={s.filters}
      savedView={s.savedView}
      savedViewCounts={s.savedViewCounts}
      customViews={s.customViews}
      onSavedViewClick={s.handleSavedViewClick}
      onPlatformToggle={(id) => s.setPlatformFilter(toggle(s.platformFilter, id))}
      onIntentToggle={(id) => s.setIntentFilter(toggle(s.intentFilter, id))}
      onCountryToggle={(code) => s.setCountryFilter(toggle(s.countryFilter, code))}
      onScoreRangeChange={(v) => s.setScoreRange(v)}
      onRiskToggle={(v) => s.setHasRiskFilter(v)}
      onSaveView={s.handleSaveView}
      onDeleteCustomView={(id) =>
        s.setCustomViews((prev) => prev.filter((v) => v.id !== id))
      }
    />
  );

  return (
    <div
      className="flex flex-col gap-4"
      style={{ height: "calc(100vh - 7rem)" }}
    >
      <KpiStrip
        kpis={s.kpis}
        range={s.range}
        onRangeChange={s.setRange}
        activeKpi={s.activeKpi}
        onKpiClick={s.handleKpiClick}
      />

      <div className="flex-1 min-h-0 flex border rounded-xl overflow-hidden bg-surface shadow-sm-signal">
        {!s.isMobile && <div className="hidden md:flex">{filterRailEl}</div>}

        <ConversationList
          filtered={s.filtered}
          loading={s.loading}
          error={null}
          selectedId={s.selectedId}
          checkedIds={s.checkedSet}
          sortKey={s.sortKey}
          chips={s.chips}
          onSortChange={s.setSortKey}
          onSelect={s.handleSelect}
          onToggleCheck={s.handleToggleCheck}
          onClearFilters={s.handleClearFilters}
        />

        {s.isLarge && !s.inspectorCollapsed && (
          <aside className="w-[420px] shrink-0 border-l bg-surface flex flex-col">
            {inspectorEl}
          </aside>
        )}
        {s.isLarge && s.inspectorCollapsed && (
          <button
            type="button"
            onClick={() => s.setInspectorCollapsed(false)}
            aria-label="Expand inspector"
            className="w-8 border-l bg-surface hover:bg-surface-sunk flex items-center justify-center focus-visible:outline-none"
          >
            <span className="rotate-90 text-xs font-medium text-text-muted whitespace-nowrap">
              Inspector
            </span>
          </button>
        )}
      </div>

      {!s.isLarge && (
        <Sheet
          open={!!s.selectedId}
          onOpenChange={(o) => {
            if (!o) s.setSelectedId(null);
          }}
        >
          <SheetContent
            side="right"
            className="w-full sm:w-[420px] p-0 flex flex-col"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>Conversation inspector</SheetTitle>
            </SheetHeader>
            {inspectorEl}
          </SheetContent>
        </Sheet>
      )}

      <div role="status" aria-live="polite" className="sr-only">
        {s.announcement}
      </div>

      <BulkActionBar
        selected={s.selectedConvos}
        onClear={() => s.setSelectedIds([])}
        onAfterAction={() => s.setSelectedIds([])}
      />
    </div>
  );
}
