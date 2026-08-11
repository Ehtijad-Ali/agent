"use client";

import * as React from "react";
import { Check, X, Clock, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  PlatformBadge,
  IntentPill,
  RiskPill,
  ScoreArc,
} from "@/components/signal/primitives";
import { formatDistanceToNow } from "date-fns";
import type { Conversation } from "@/lib/types";
import { cn } from "@/lib/utils";

interface TriageCardProps {
  conversation: Conversation;
  maxLength: number;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onApprove: () => void;
  onReject: () => void;
  onSnooze: () => void;
  onEdit: () => void;
  onVariantChange: (delta: number) => void;
  onEditReply: (text: string) => void;
}

const ARROW_BTN =
  "inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-surface text-text-muted hover:bg-surface-sunk hover:text-text transition-colors focus-visible:outline-none disabled:opacity-40 disabled:cursor-not-allowed";

/**
 * TriageCard — the presentational UI for a single conversation card.
 * The parent (TriageView) handles depth-based transforms (peeking)
 * and mobile drag. This component just renders the card content:
 * header, risk/intent pills, message quote, keyword chips, AI
 * summary, reply variant editor with ◀ ▶ switcher, and the
 * Approve / Reject / Snooze / Edit footer.
 */
export function TriageCard({
  conversation: c,
  maxLength,
  textareaRef,
  onApprove,
  onReject,
  onSnooze,
  onEdit,
  onVariantChange,
  onEditReply,
}: TriageCardProps) {
  const draft = c.editedReply ?? c.replyVariants[c.selectedVariant]?.text ?? "";
  const variant = c.replyVariants[c.selectedVariant];
  const totalVariants = c.replyVariants.length;
  const underLength = draft.length <= maxLength;

  return (
    <div className="flex flex-col h-full bg-surface border rounded-xl shadow-lg-signal overflow-hidden">
      {/* Header — platform / community / author / time / score */}
      <div className="flex items-start gap-3 px-4 py-3 border-b bg-surface-sunk/40 shrink-0">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs">
            <PlatformBadge platform={c.platform} />
            <span className="text-text-muted/50" aria-hidden>
              /
            </span>
            <span className="font-mono text-text-muted truncate">
              {c.community}
            </span>
          </div>
          <div className="flex items-center gap-1.5 mt-1 text-xs text-text-muted">
            <span className="font-mono">{c.authorPseudonym}</span>
            <span aria-hidden>·</span>
            <span>
              {formatDistanceToNow(new Date(c.postedAt), { addSuffix: true })}
            </span>
          </div>
        </div>
        <div className="shrink-0">
          <ScoreArc score={c.score} intent={c.intent} size={40} />
        </div>
      </div>

      {/* Body — scrollable */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
        {/* Intent + risk pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <IntentPill intent={c.intent} />
          {c.riskFlags.map((flag) => (
            <RiskPill key={flag} flag={flag} />
          ))}
        </div>

        {/* Quoted message */}
        <blockquote
          className="border-l-4 border-primary pl-4 italic text-sm text-text leading-relaxed"
        >
          {c.message}
        </blockquote>

        {/* Matched keywords */}
        {c.matchedKeywords.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] uppercase tracking-wide text-text-muted font-semibold">
              Keywords
            </span>
            {c.matchedKeywords.map((kw) => (
              <Badge
                key={kw}
                variant="outline"
                className="bg-primary-soft text-primary border-transparent font-mono text-[10px]"
              >
                {kw}
              </Badge>
            ))}
          </div>
        )}

        {/* AI summary */}
        <div className="space-y-1">
          <p className="text-[10px] uppercase tracking-wide text-text-muted font-semibold">
            AI summary
          </p>
          <p className="text-sm text-text leading-relaxed">{c.summary}</p>
        </div>

        {/* Reply variant + editor */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase tracking-wide text-text-muted font-semibold">
              Reply draft
            </p>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                className={ARROW_BTN}
                onClick={() => onVariantChange(-1)}
                aria-label="Previous reply variant"
                disabled={totalVariants <= 1}
              >
                <span aria-hidden>◀</span>
              </button>
              <span className="font-mono text-[10px] tabular-nums text-text-muted min-w-[100px] text-center capitalize">
                {variant?.tone ?? "—"} · {c.selectedVariant + 1}/{totalVariants}
              </span>
              <button
                type="button"
                className={ARROW_BTN}
                onClick={() => onVariantChange(1)}
                aria-label="Next reply variant"
                disabled={totalVariants <= 1}
              >
                <span aria-hidden>▶</span>
              </button>
            </div>
          </div>
          <Textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => onEditReply(e.target.value)}
            className="min-h-20 text-sm leading-relaxed resize-y"
            aria-label="Reply draft"
          />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">
              Press{" "}
              <kbd className="font-mono px-1 rounded border bg-surface-sunk">
                E
              </kbd>{" "}
              to edit
            </span>
            <span
              className={cn(
                "text-[10px] font-mono tabular-nums",
                underLength ? "text-text-muted" : "text-risk",
              )}
            >
              {draft.length}/{maxLength}
            </span>
          </div>
        </div>
      </div>

      {/* Footer — action buttons */}
      <div className="border-t bg-surface p-3 flex flex-wrap items-center gap-1.5 shrink-0">
        <Button
          size="sm"
          onClick={onApprove}
          className="bg-success text-white hover:bg-success/90"
          aria-label="Approve (A)"
        >
          <Check className="h-3.5 w-3.5" />
          Approve
          <span className="text-[10px] opacity-70 ml-0.5">A</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onReject}
          aria-label="Reject (R)"
        >
          <X className="h-3.5 w-3.5" />
          Reject
          <span className="text-[10px] opacity-70 ml-0.5">R</span>
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onSnooze}
          aria-label="Snooze 24 hours (S)"
        >
          <Clock className="h-3.5 w-3.5" />
          Snooze
          <span className="text-[10px] opacity-70 ml-0.5">S</span>
        </Button>
        <div className="flex-1" />
        <Button variant="ghost" size="sm" onClick={onEdit} aria-label="Edit reply (E)">
          <Pencil className="h-3.5 w-3.5" />
          Edit
          <span className="text-[10px] opacity-70 ml-0.5">E</span>
        </Button>
      </div>
    </div>
  );
}
