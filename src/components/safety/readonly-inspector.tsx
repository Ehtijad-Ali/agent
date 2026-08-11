"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RiskPill } from "@/components/signal/primitives";
import { PLATFORMS } from "@/lib/constants";
import type { Conversation, RiskFlag } from "@/lib/types";

/* ============================================================
   Readonly inspector — modal dialog for blocked items.
   No action buttons — the row is auditable but never repliable.
   ============================================================ */

function formatDay(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

interface ReadonlyInspectorProps {
  conversation: Conversation | null;
  flag: RiskFlag | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReadonlyInspector({
  conversation,
  flag,
  open,
  onOpenChange,
}: ReadonlyInspectorProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-base">
            Blocked item (read-only)
          </DialogTitle>
          <DialogDescription>
            A safety rule blocked this conversation. It is here for audit only, so
            there is no reply action.
          </DialogDescription>
        </DialogHeader>
        {conversation && flag && (
          <ReadonlyBody conversation={conversation} flag={flag} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ReadonlyBody({
  conversation,
  flag,
}: {
  conversation: Conversation;
  flag: RiskFlag;
}) {
  const meta = PLATFORMS[conversation.platform];
  return (
    <div className="space-y-4 text-sm">
      <div className="grid grid-cols-2 gap-3">
        <Field label="ID">
          <span className="font-mono text-xs">{conversation.id}</span>
        </Field>
        <Field label="Platform">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden>{meta.glyph}</span>
            <span>{meta.label}</span>
          </span>
        </Field>
        <Field label="Author (pseudonym)">
          <span className="font-mono text-xs">
            {conversation.authorPseudonym}
          </span>
        </Field>
        <Field label="Posted">
          <span className="tabular-nums">
            {formatDay(conversation.postedAt)}
          </span>
        </Field>
        <Field label="Score">
          <span className="font-mono tabular-nums">{conversation.score}</span>
        </Field>
        <Field label="Risk flag">
          <RiskPill flag={flag} />
        </Field>
      </div>
      <Field label="Message">
        <blockquote className="border-l-2 border-primary/40 pl-3 pr-2 py-2 italic text-text bg-surface-sunk/40 rounded-r-md">
          {conversation.message}
        </blockquote>
      </Field>
      <Field label="Auto-detected reason">
        <p className="text-text-muted">{conversation.summary}</p>
      </Field>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
        {label}
      </p>
      <div className="text-text">{children}</div>
    </div>
  );
}
