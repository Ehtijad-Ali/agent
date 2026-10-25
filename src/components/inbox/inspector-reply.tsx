"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Check, Copy, RefreshCw } from "lucide-react";
import type { Conversation } from "@/lib/types";

const TONES = [
  { id: "helpful", label: "Helpful", hint: "Warm + thorough" },
  { id: "concise", label: "Concise", hint: "One-liner" },
  { id: "conversational", label: "Conversational", hint: "Friendly chat" },
] as const;

interface ReplyProps {
  conversation: Conversation;
  maxLength: number;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onVariantChange: (index: number) => void;
  onEditReply: (text: string) => void;
  onToast: (msg: string) => void;
}

export function InspectorReply({
  conversation: c,
  maxLength,
  textareaRef,
  onVariantChange,
  onEditReply,
  onToast,
}: ReplyProps) {
  const draft = c.editedReply ?? c.replyVariants[c.selectedVariant]?.text ?? "";

  const hasUrl = /https?:\/\//i.test(draft);
  const hasDisclosure = /disclosure|with Join All Bettors/i.test(draft);
  const hasFtpClause = /free.to.play|no real money|no deposits/i.test(draft);
  const underLength = draft.length <= maxLength;

  const handleRegenerate = () => {
    const next = (c.selectedVariant + 1) % c.replyVariants.length;
    onVariantChange(next);
    onToast(`Switched to ${c.replyVariants[next].tone} variant`);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(draft);
      onToast("Draft copied to clipboard");
    } catch {
      onToast("Couldn't copy — select the text manually");
    }
  };

  return (
    <div className="space-y-4 px-4 py-4 overflow-y-auto">
      {/* Tone variant cards */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Tone
        </p>
        <div className="grid grid-cols-3 gap-2">
          {TONES.map((tone, i) => {
            const active = c.selectedVariant === i;
            return (
              <button
                key={tone.id}
                type="button"
                onClick={() => onVariantChange(i)}
                aria-pressed={active}
                className={cn(
                  "rounded-md border p-2 text-left transition-all focus-visible:outline-none",
                  active
                    ? "border-primary ring-1 ring-primary/30 bg-primary-soft"
                    : "border-border hover:border-text-muted/40 bg-surface",
                )}
              >
                <p
                  className={cn(
                    "text-xs font-medium",
                    active ? "text-primary" : "text-text",
                  )}
                >
                  {tone.label}
                </p>
                <p className="text-[10px] text-text-muted mt-0.5">
                  {tone.hint}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Draft editor */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Draft reply
          </p>
          <span
            className={cn(
              "text-xs font-mono tabular-nums",
              underLength ? "text-text-muted" : "text-risk",
            )}
          >
            {draft.length}/{maxLength}
          </span>
        </div>
        <Textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => onEditReply(e.target.value)}
          className="min-h-32 text-sm leading-relaxed resize-y"
          aria-label="Reply draft"
        />
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRegenerate}>
            <RefreshCw className="h-3.5 w-3.5" />
            Regenerate
          </Button>
          <Button variant="ghost" size="sm" onClick={handleCopy}>
            <Copy className="h-3.5 w-3.5" />
            Copy for manual posting
          </Button>
        </div>
      </div>

      {/* Compliance checklist */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Compliance
        </p>
        <ul className="space-y-1.5">
          <ComplianceRow ok={hasUrl} label="URL included" />
          <ComplianceRow ok={hasDisclosure} label="Connection disclosed" />
          <ComplianceRow
            ok={hasFtpClause}
            label="“free-to-play, not real money”"
          />
          <ComplianceRow ok={underLength} label={`Under ${maxLength} chars`} />
        </ul>
      </div>
    </div>
  );
}

function ComplianceRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <span
        className={cn(
          "inline-flex h-4 w-4 items-center justify-center rounded-full border",
          ok
            ? "bg-success/15 border-success/40 text-success"
            : "bg-surface-sunk border-border text-text-muted",
        )}
        aria-hidden
      >
        {ok && <Check className="h-3 w-3" />}
      </span>
      <span className={ok ? "text-text" : "text-text-muted"}>{label}</span>
      <Badge
        variant="outline"
        className={cn(
          "ml-auto text-[10px] border-transparent",
          ok
            ? "bg-success/10 text-success"
            : "bg-surface-sunk text-text-muted",
        )}
      >
        {ok ? "Pass" : "Check"}
      </Badge>
    </li>
  );
}
