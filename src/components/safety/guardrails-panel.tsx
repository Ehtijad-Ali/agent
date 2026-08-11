"use client";

import * as React from "react";
import {
  ShieldCheck,
  ShieldX,
  ShieldAlert,
  Users,
  Eye,
  Link2,
  Gauge,
  ScrollText,
  type LucideIcon,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

/* ============================================================
   Guardrails panel — the "trust" panel for the Safety view.
   A vertical list of plain-English guardrail cards. Each card
   has an icon, title, paragraph, a status dot, and a "View rule"
   link that scrolls to / navigates to the related rule below.
   ============================================================ */

interface Guardrail {
  id: string;
  icon: LucideIcon;
  title: string;
  body: string;
  /** Anchor of a section on the Safety page to scroll to, or
   *  the literal string "tuning" to navigate to the Tuning view. */
  ruleTarget: string;
}

const GUARDRAILS: Guardrail[] = [
  {
    id: "g1",
    icon: ShieldCheck,
    title: "Nothing posts without human approval",
    body: "Replies stay as drafts until someone reviews and approves them. Signal surfaces candidates and writes suggestions. It does not post.",
    ruleTarget: "tuning",
  },
  {
    id: "g2",
    icon: ShieldAlert,
    title: "Under-18 authors are blocked",
    body: "If a message suggests the author is under 18, it goes straight to the blocked bin and no reply is drafted for it. The item stays visible so the decision can be audited.",
    ruleTarget: "#blocked-items",
  },
  {
    id: "g3",
    icon: ShieldX,
    title: "Real-money requests are rejected",
    body: "Join All Bettors is free-to-play only. Messages asking about real-money gambling, betting sites, crypto or withdrawals are rejected automatically and kept in the blocked bin.",
    ruleTarget: "#blocked-items",
  },
  {
    id: "g4",
    icon: ShieldX,
    title: "Spam and promo bait is filtered out",
    body: "Copied templates, link farming and off-topic solicitation are caught before a reviewer ever sees them.",
    ruleTarget: "#blocked-items",
  },
  {
    id: "g5",
    icon: Users,
    title: "One reply per person, ever",
    body: "Each author is contacted at most once. If a reply already exists for that handle, their later messages are suppressed from the queue.",
    ruleTarget: "tuning",
  },
  {
    id: "g6",
    icon: ScrollText,
    title: "Every reply discloses the brand connection",
    body: "Replies state that the responder works with the brand, and note that the product is free-to-play rather than real money. Both are locked rules in the reply voice settings.",
    ruleTarget: "tuning",
  },
  {
    id: "g7",
    icon: Eye,
    title: "Public posts only, authors pseudonymised",
    body: "Only public posts are read. Handles are replaced with pseudonyms in this interface. No DMs, no private groups, no stored profile images.",
    ruleTarget: "tuning",
  },
  {
    id: "g8",
    icon: Gauge,
    title: "Rate caps per platform, plus a daily ceiling",
    body: "Outbound volume is capped per platform per hour, with a hard limit on approved replies per day. The usage meter below shows where you currently sit against both.",
    ruleTarget: "#usage-meter",
  },
  {
    id: "g9",
    icon: Link2,
    title: "Platform terms of service are respected",
    body: "Discovery, scoring and reply cadence follow the published terms for each platform we read. Current ToS links are below.",
    ruleTarget: "#tos-links",
  },
];

interface GuardrailsPanelProps {
  /** Called when a guardrail's "View rule" link needs to leave the
   *  Safety view (currently only for the "tuning" target). */
  onNavigateAway?: (target: "tuning") => void;
}

export function GuardrailsPanel({ onNavigateAway }: GuardrailsPanelProps) {
  const handleViewRule = React.useCallback(
    (target: string) => {
      if (target === "tuning") {
        onNavigateAway?.("tuning");
        return;
      }
      if (target.startsWith("#")) {
        const el = document.getElementById(target.slice(1));
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    },
    [onNavigateAway],
  );

  return (
    <Card className="py-0">
      <CardHeader className="px-6 pt-6 pb-3">
        <CardTitle className="text-base">Guardrails</CardTitle>
        <p className="text-sm text-text-muted mt-1">
          Nine non-negotiable rules enforced automatically. Trust is a
          feature, not a footnote.
        </p>
      </CardHeader>
      <CardContent className="px-2 pb-3">
        <ul className="divide-y divide-border" aria-label="Guardrail list">
          {GUARDRAILS.map((g) => (
            <GuardrailRow key={g.id} guardrail={g} onViewRule={handleViewRule} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function GuardrailRow({
  guardrail,
  onViewRule,
}: {
  guardrail: Guardrail;
  onViewRule: (target: string) => void;
}) {
  const Icon = guardrail.icon;
  return (
    <li className="px-4 py-4 flex gap-4 hover:bg-surface-sunk/40 transition-colors">
      <div
        className={cn(
          "shrink-0 mt-0.5 rounded-md p-2",
          "bg-primary-soft text-primary",
        )}
        aria-hidden
      >
        <Icon className="h-4 w-4" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <h3 className="text-sm font-medium text-text">{guardrail.title}</h3>
          <span
            className="inline-flex items-center gap-1.5 text-xs font-medium text-success shrink-0"
            aria-label="Status: active"
          >
            <span
              className="h-2 w-2 rounded-full bg-success"
              aria-hidden
            />
            Active
          </span>
        </div>
        <p className="mt-1.5 text-sm text-text-muted leading-relaxed">
          {guardrail.body}
        </p>
        <button
          type="button"
          onClick={() => onViewRule(guardrail.ruleTarget)}
          className={cn(
            "mt-2 inline-flex items-center gap-1 text-xs font-medium",
            "text-primary hover:underline focus-visible:outline-none",
          )}
          aria-label={`View rule: ${guardrail.title}`}
        >
          View rule
          <span aria-hidden>→</span>
        </button>
      </div>
    </li>
  );
}
