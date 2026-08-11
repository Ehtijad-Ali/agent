"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { PartyPopper, Check, X, Clock, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface TriageSessionCounts {
  approved: number;
  rejected: number;
  snoozed: number;
}

/**
 * TriageEmpty — end-of-queue celebration shown when the triage queue
 * has been fully cleared. Renders a centered PartyPopper icon, the
 * "Queue cleared!" headline, a session summary line, and a
 * "Back to inbox" button that flips `currentView` back to "inbox".
 */
export function TriageEmpty({
  counts,
  reviewedTotal,
  onBackToInbox,
}: {
  counts: TriageSessionCounts;
  reviewedTotal: number;
  onBackToInbox: () => void;
}) {
  const stats = [
    { icon: Check, label: "approved", value: counts.approved, tone: "text-success" },
    { icon: X, label: "rejected", value: counts.rejected, tone: "text-risk" },
    { icon: Clock, label: "snoozed", value: counts.snoozed, tone: "text-text-muted" },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: 8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className="flex flex-col items-center justify-center text-center px-6 py-12 max-w-md mx-auto"
      role="status"
      aria-live="polite"
    >
      <div className="rounded-md p-3 bg-primary-soft text-primary mb-4">
        <PartyPopper className="h-7 w-7" aria-hidden />
      </div>
      <h2 className="text-xl font-semibold text-text">Queue cleared!</h2>
      <p className="text-sm text-text-muted mt-2 leading-relaxed">
        You reviewed{" "}
        <span className="font-mono font-semibold text-text">{reviewedTotal}</span>{" "}
        conversation{reviewedTotal === 1 ? "" : "s"} · approved{" "}
        <span className="font-mono text-success">{counts.approved}</span> ·
        rejected{" "}
        <span className="font-mono text-risk">{counts.rejected}</span> ·
        snoozed{" "}
        <span className="font-mono text-text-muted">{counts.snoozed}</span>.
      </p>

      <ul className="grid grid-cols-3 gap-2 w-full mt-6">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <li
              key={s.label}
              className="flex flex-col items-center gap-1 rounded-md border bg-surface px-3 py-3"
            >
              <Icon className={`h-4 w-4 ${s.tone}`} aria-hidden />
              <span className="font-mono text-lg font-semibold tabular-nums text-text">
                {s.value}
              </span>
              <span className="text-[10px] uppercase tracking-wide text-text-muted">
                {s.label}
              </span>
            </li>
          );
        })}
      </ul>

      <Button
        variant="default"
        size="sm"
        onClick={onBackToInbox}
        className="mt-6"
        aria-label="Back to inbox"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to inbox
      </Button>
    </motion.div>
  );
}
