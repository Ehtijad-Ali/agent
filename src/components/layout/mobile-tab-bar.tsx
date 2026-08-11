"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import { NAV_ITEMS } from "@/lib/constants";
import {
  Inbox,
  Layers,
  BarChart3,
  FlaskConical,
  SlidersHorizontal,
  ShieldCheck,
  History,
} from "lucide-react";
import { cn } from "@/lib/utils";

const ICONS = {
  inbox: Inbox,
  triage: Layers,
  insights: BarChart3,
  playground: FlaskConical,
  tuning: SlidersHorizontal,
  safety: ShieldCheck,
  activity: History,
} as const;

/**
 * MobileTabBar — replaces the sidebar on screens < 768px.
 */
export function MobileTabBar() {
  const currentView = useSignalStore((s) => s.currentView);
  const setCurrentView = useSignalStore((s) => s.setCurrentView);

  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-30 border-t bg-surface flex items-stretch h-14 px-1"
      aria-label="Mobile navigation"
      style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
    >
      {NAV_ITEMS.map((item) => {
        const Icon = ICONS[item.id];
        const active = currentView === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setCurrentView(item.id)}
            aria-current={active ? "page" : undefined}
            aria-label={item.label}
            className={cn(
              "flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors",
              active
                ? "text-primary"
                : "text-text-muted hover:text-text",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            <span>{item.label.split(" ")[0]}</span>
          </button>
        );
      })}
    </nav>
  );
}
