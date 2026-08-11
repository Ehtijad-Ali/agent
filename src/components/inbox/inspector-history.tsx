"use client";

import { formatDistanceToNow, format } from "date-fns";
import { cn } from "@/lib/utils";
import { History as HistoryIcon } from "lucide-react";
import type { Conversation } from "@/lib/types";

export function InspectorHistory({ c }: { c: Conversation }) {
  const entries = [...c.history].reverse();

  if (entries.length === 0) {
    return (
      <div className="px-4 py-8 text-center text-sm text-text-muted">
        No history yet for this conversation.
      </div>
    );
  }

  return (
    <ol className="px-4 py-4 space-y-0 overflow-y-auto" aria-label="History timeline">
      {entries.map((entry, i) => {
        const isLast = i === entries.length - 1;
        const date = new Date(entry.at);
        return (
          <li key={`${entry.at}-${i}`} className="relative flex gap-3 pb-4">
            {/* Timeline line */}
            {!isLast && (
              <span
                aria-hidden
                className="absolute left-[7px] top-5 bottom-0 w-px bg-border"
              />
            )}
            <span
              aria-hidden
              className={cn(
                "mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border-2",
                isLast
                  ? "border-primary bg-primary-soft"
                  : "border-border bg-surface",
              )}
            >
              <HistoryIcon className="h-2 w-2 text-text-muted" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-text leading-snug">{entry.action}</p>
              <p className="mt-0.5 text-xs text-text-muted">
                <span className="font-mono">{entry.actor}</span>
                {" · "}
                <span title={format(date, "d MMM yyyy · HH:mm:ss")}>
                  {formatDistanceToNow(date, { addSuffix: true })}
                </span>
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
