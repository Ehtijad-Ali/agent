"use client";

import * as React from "react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import {
  PlatformBadge,
  CountryFlag,
  RiskPill,
  ScoreArc,
} from "@/components/signal/primitives";
import { Check, X, Clock } from "lucide-react";
import type { Conversation } from "@/lib/types";

/** Fixed row height for windowed rendering. */
export const ROW_HEIGHT = 92;

interface RowProps {
  conversation: Conversation;
  selected: boolean;
  checked: boolean;
  focused: boolean;
  onSelect: () => void;
  onToggleCheck: (shiftKey: boolean) => void;
}

/**
 * Single conversation row in the inbox list. Renders platform, country,
 * excerpt, community, relative time, risk pill, and a score arc. Row
 * states: unread (teal bar), selected (primary-soft bg), decided (60%
 * opacity + check/cross icon).
 */
export function ConversationRow({
  conversation: c,
  selected,
  checked,
  focused,
  onSelect,
  onToggleCheck,
}: RowProps) {
  const isUnread = c.status === "new";
  const isDecided =
    c.status === "approved" ||
    c.status === "rejected" ||
    c.status === "blocked" ||
    c.status === "manually_posted";
  const isSnoozed = c.status === "snoozed";

  const decisionIcon =
    c.status === "approved" || c.status === "manually_posted" ? (
      <Check className="h-3.5 w-3.5 text-success" aria-label="Approved" />
    ) : c.status === "rejected" || c.status === "blocked" ? (
      <X className="h-3.5 w-3.5 text-risk" aria-label="Rejected" />
    ) : isSnoozed ? (
      <Clock className="h-3.5 w-3.5 text-text-muted" aria-label="Snoozed" />
    ) : null;

  return (
    <div
      role="option"
      aria-selected={selected}
      tabIndex={focused ? 0 : -1}
      onClick={(e) => {
        if (e.shiftKey) {
          onToggleCheck(true);
        } else {
          onSelect();
        }
      }}
      onKeyDown={(e) => {
        if (e.key === " ") {
          e.preventDefault();
          onToggleCheck(e.shiftKey);
        } else if (e.key === "Enter") {
          e.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        "relative flex items-stretch gap-3 px-4 cursor-pointer border-b border-border/60 transition-colors focus:outline-none",
        selected ? "bg-primary-soft" : "bg-surface hover:bg-surface-sunk/50",
        focused && "ring-2 ring-primary ring-inset",
        isDecided && "opacity-60",
      )}
      style={{ height: ROW_HEIGHT }}
    >
      {/* Unread bar */}
      {isUnread && (
        <span
          aria-hidden
          className="absolute left-0 top-0 bottom-0 w-[3px] bg-primary"
        />
      )}

      {/* Checkbox */}
      <div
        data-checkbox
        className="flex items-center"
        onClick={(e) => {
          e.stopPropagation();
          onToggleCheck(e.shiftKey);
        }}
      >
        <Checkbox
          checked={checked}
          aria-label={`Select conversation ${c.id}`}
          tabIndex={-1}
        />
      </div>

      {/* Main content */}
      <div className="flex-1 min-w-0 flex flex-col justify-center">
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <PlatformBadge platform={c.platform} />
          <CountryFlag code={c.country} />
          <span className="font-mono truncate">{c.community}</span>
          <span className="text-text-muted/60" aria-hidden>
            ·
          </span>
          <span className="whitespace-nowrap">
            {formatDistanceToNow(new Date(c.postedAt), { addSuffix: true })}
          </span>
          {decisionIcon}
        </div>
        <p className="mt-1 text-sm text-text line-clamp-2 leading-snug">
          {c.message}
        </p>
        {c.riskFlags.length > 0 && (
          <div className="mt-1 flex items-center gap-1 flex-wrap">
            {c.riskFlags.slice(0, 2).map((f) => (
              <RiskPill key={f} flag={f} />
            ))}
            {c.riskFlags.length > 2 && (
              <span className="text-xs text-text-muted">
                +{c.riskFlags.length - 2}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Score arc */}
      <div className="flex items-center pl-2 pr-1">
        <ScoreArc score={c.score} intent={c.intent} size={44} />
      </div>
    </div>
  );
}
