"use client";

import * as React from "react";
import { AppShell } from "@/components/layout/app-shell";
import { InboxView } from "@/components/views/inbox-view";
import { TriageView } from "@/components/views/triage-view";
import { TuningView } from "@/components/views/tuning-view";
import { PlaygroundView } from "@/components/views/playground-view";
import { InsightsView } from "@/components/views/insights-view";
import { SafetyView } from "@/components/views/safety-view";
import { ActivityView } from "@/components/views/activity-view";
import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";
import { useSignalStore } from "@/stores/signal-store";
import type { ViewId } from "@/lib/constants";

/**
 * Single-page app — only `/` route is visible to the sandbox preview.
 * The ViewSwitch dispatches on `currentView` (set by the sidebar /
 * mobile tab bar / ⌘K palette).
 *
 * First-run users see the OnboardingWizard in place of the view. They
 * can skip it (which sets onboardingComplete=true). Re-runnable from
 * a help menu / Safety view.
 */
function renderView(view: ViewId): React.ReactNode {
  switch (view) {
    case "triage":
      return <TriageView />;
    case "tuning":
      return <TuningView />;
    case "playground":
      return <PlaygroundView />;
    case "insights":
      return <InsightsView />;
    case "safety":
      return <SafetyView />;
    case "activity":
      return <ActivityView />;
    case "inbox":
    default:
      return <InboxView />;
  }
}

export default function Home() {
  const currentView = useSignalStore((s) => s.currentView);
  const onboardingComplete = useSignalStore((s) => s.onboardingComplete);
  const loading = useSignalStore((s) => s.loading);

  // While the store is hydrating from localStorage, show a brief skeleton
  // to avoid SSR mismatch flashes.
  if (loading && typeof window !== "undefined") {
    // Only show loading briefly; once hydrated the gate below takes over.
  }

  if (!onboardingComplete) {
    return <OnboardingWizard />;
  }

  return <AppShell>{renderView(currentView)}</AppShell>;
}
