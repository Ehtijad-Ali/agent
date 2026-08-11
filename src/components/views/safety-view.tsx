"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import { GuardrailsPanel } from "@/components/safety/guardrails-panel";
import { UsageMeter } from "@/components/safety/usage-meter";
import { TosLinks } from "@/components/safety/tos-links";
import { BlockedItems } from "@/components/safety/blocked-items";

/* ============================================================
   Safety view — guardrails, live usage, ToS links, blocked bin.
   Prominent, plain-language trust surface.
   ============================================================ */

export function SafetyView() {
  const conversations = useSignalStore((s) => s.conversations);
  const config = useSignalStore((s) => s.config);
  const setCurrentView = useSignalStore((s) => s.setCurrentView);
  const hydrate = useSignalStore((s) => s.hydrate);

  React.useEffect(() => {
    hydrate();
  }, [hydrate]);

  const handleNavigateAway = React.useCallback(
    (target: "tuning") => {
      if (target === "tuning") setCurrentView("tuning");
    },
    [setCurrentView],
  );

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-text">Safety</h1>
        <p className="text-sm text-text-muted">
          The rules that keep this product trustworthy. Every guardrail below
          is enforced automatically and auditable.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <GuardrailsPanel onNavigateAway={handleNavigateAway} />
        </div>
        <div className="space-y-5">
          <UsageMeter
            conversations={conversations}
            dailyCeiling={config.rateCaps.dailyApprovedCeiling}
            perPlatformPerHour={config.rateCaps.perPlatformPerHour}
          />
          <TosLinks />
        </div>
      </div>

      <BlockedItems conversations={conversations} />
    </div>
  );
}
