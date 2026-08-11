"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { X, Inbox as InboxIcon, ArrowUpDown } from "lucide-react";
import { ConversationRow, ROW_HEIGHT } from "./conversation-row";
import { SignalSkeleton, EmptyState } from "@/components/signal/primitives";
import type { Conversation } from "@/lib/types";
import type { FilterChip, SortKey } from "./types";

const OVERSCAN = 4;

interface ListProps {
  filtered: Conversation[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  checkedIds: Set<string>;
  sortKey: SortKey;
  chips: FilterChip[];
  onSortChange: (k: SortKey) => void;
  onSelect: (id: string) => void;
  onToggleCheck: (id: string, shiftKey: boolean) => void;
  onClearFilters: () => void;
}

export function ConversationList({
  filtered,
  loading,
  error,
  selectedId,
  checkedIds,
  sortKey,
  chips,
  onSortChange,
  onSelect,
  onToggleCheck,
  onClearFilters,
}: ListProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = React.useState(0);
  const [viewportH, setViewportH] = React.useState(600);
  const [focusedIdx, setFocusedIdx] = React.useState(0);

  // Track viewport height for windowing.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setViewportH(e.contentRect.height);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Keep focused index in bounds when list changes.
  React.useEffect(() => {
    if (focusedIdx >= filtered.length) {
      setFocusedIdx(Math.max(0, filtered.length - 1));
    }
  }, [filtered.length, focusedIdx]);

  const totalHeight = filtered.length * ROW_HEIGHT;
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const endIndex = Math.min(
    filtered.length,
    Math.ceil((scrollTop + viewportH) / ROW_HEIGHT) + OVERSCAN,
  );
  const visible = filtered.slice(startIndex, endIndex);
  const offsetY = startIndex * ROW_HEIGHT;

  const scrollToIndex = React.useCallback(
    (idx: number) => {
      const el = scrollRef.current;
      if (!el) return;
      const top = idx * ROW_HEIGHT;
      if (top < el.scrollTop) {
        el.scrollTop = top;
      } else if (top + ROW_HEIGHT > el.scrollTop + el.clientHeight) {
        el.scrollTop = top + ROW_HEIGHT - el.clientHeight;
      }
    },
    [],
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (filtered.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = Math.min(filtered.length - 1, focusedIdx + 1);
      setFocusedIdx(next);
      scrollToIndex(next);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const next = Math.max(0, focusedIdx - 1);
      setFocusedIdx(next);
      scrollToIndex(next);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const c = filtered[focusedIdx];
      if (c) onSelect(c.id);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onSelect("");
    }
  };

  return (
    <section
      className="flex-1 min-w-0 flex flex-col bg-surface border-r"
      aria-label="Conversation list"
    >
      {/* Toolbar: sort + count + chips */}
      <div className="px-4 pt-3 pb-2 border-b space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="font-mono tabular-nums text-text font-semibold">
              {filtered.length}
            </span>
            <span>conversations</span>
          </div>
          <div className="flex items-center gap-1.5">
            <ArrowUpDown className="h-3.5 w-3.5 text-text-muted" aria-hidden />
            <Select
              value={sortKey}
              onValueChange={(v) => onSortChange(v as SortKey)}
            >
              <SelectTrigger size="sm" className="h-7 w-[150px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="relevance">Relevance</SelectItem>
                <SelectItem value="recency">Recency</SelectItem>
                <SelectItem value="intent">Intent</SelectItem>
                <SelectItem value="platform">Platform</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Active filter chips */}
        {chips.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {chips.map((chip) => (
              <Badge
                key={chip.id}
                variant="secondary"
                className="gap-1 pr-1 font-normal"
              >
                {chip.label}
                <button
                  type="button"
                  onClick={chip.onRemove}
                  aria-label={`Remove filter ${chip.label}`}
                  className="rounded-sm p-0.5 hover:bg-surface-sunk"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs text-text-muted"
              onClick={onClearFilters}
            >
              Clear all
            </Button>
          </div>
        )}
      </div>

      {/* List body */}
      <div
        ref={scrollRef}
        role="listbox"
        aria-label="Conversations"
        tabIndex={0}
        onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
        onKeyDown={onKeyDown}
        className="flex-1 overflow-y-auto outline-none relative"
      >
        {error ? (
          <ErrorState message={error} onRetry={() => onClearFilters()} />
        ) : loading ? (
          <div className="p-4 space-y-2">
            <SignalSkeleton lines={8} />
            <SignalSkeleton lines={8} />
            <SignalSkeleton lines={8} />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={InboxIcon}
            title="No conversations match"
            description="Nothing matches the current filters. Widen them, or clear them to see everything."
            action={
              chips.length > 0 ? (
                <Button variant="outline" size="sm" onClick={onClearFilters}>
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div style={{ height: totalHeight, position: "relative" }}>
            <div
              style={{
                transform: `translateY(${offsetY}px)`,
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
              }}
            >
              {visible.map((c, i) => {
                const idx = startIndex + i;
                return (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    selected={selectedId === c.id}
                    checked={checkedIds.has(c.id)}
                    focused={focusedIdx === idx}
                    onSelect={() => {
                      setFocusedIdx(idx);
                      onSelect(c.id);
                    }}
                    onToggleCheck={(shiftKey) =>
                      onToggleCheck(c.id, shiftKey)
                    }
                  />
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="p-6">
      <EmptyState
        icon={InboxIcon}
        title="Something went wrong"
        description={message}
        action={
          <Button variant="outline" size="sm" onClick={onRetry}>
            Try again
          </Button>
        }
      />
    </div>
  );
}

