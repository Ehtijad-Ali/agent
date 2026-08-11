"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { useSignalStore } from "@/stores/signal-store";
import { NAV_ITEMS, type ViewId } from "@/lib/constants";
import {
  Inbox,
  Layers,
  BarChart3,
  FlaskConical,
  SlidersHorizontal,
  ShieldCheck,
  History,
  Radar,
  ChevronLeft,
  ChevronRight,
  Menu,
} from "lucide-react";
import { TopBar } from "./top-bar";
import { CommandPalette } from "./command-palette";
import { MobileTabBar } from "./mobile-tab-bar";

const ICONS: Record<ViewId, React.ComponentType<{ className?: string }>> = {
  inbox: Inbox,
  triage: Layers,
  insights: BarChart3,
  playground: FlaskConical,
  tuning: SlidersHorizontal,
  safety: ShieldCheck,
  activity: History,
};

/**
 * AppShell — persistent sidebar (collapsible), top bar, command palette.
 * Mobile (<768px): bottom tab bar instead of sidebar.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const currentView = useSignalStore((s) => s.currentView);
  const setCurrentView = useSignalStore((s) => s.setCurrentView);

  return (
    <div className="min-h-screen flex bg-canvas text-text">
      {/* Sidebar — desktop only */}
      <aside
        className={cn(
          "hidden md:flex flex-col border-r bg-surface transition-[width] duration-200 ease-out sticky top-0 h-screen",
          collapsed ? "w-16" : "w-60",
        )}
        aria-label="Primary navigation"
      >
        <div
          className={cn(
            "flex items-center gap-2 h-14 px-4 border-b",
            collapsed && "justify-center px-0",
          )}
        >
          <div className="flex items-center justify-center w-8 h-8 rounded-md bg-primary text-primary-foreground">
            <Radar className="h-4 w-4" aria-hidden />
          </div>
          {!collapsed && (
            <div className="flex flex-col leading-none">
              <span className="font-semibold text-sm">Signal</span>
              <span className="text-[11px] text-text-muted">
                Join All Bettors
              </span>
            </div>
          )}
        </div>

        <nav className="flex-1 py-3 px-2 space-y-0.5" aria-label="Views">
          {NAV_ITEMS.map((item) => {
            const Icon = ICONS[item.id];
            const active = currentView === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setCurrentView(item.id)}
                aria-current={active ? "page" : undefined}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "group w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-primary-soft text-primary font-medium"
                    : "text-text-muted hover:bg-surface-sunk hover:text-text",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {!collapsed && <span className="flex-1 text-left">{item.label}</span>}
                {!collapsed && (
                  // Full chord ("G I"), not a bare letter — a lone "I" beside
                  // "Inbox" reads as part of the label rather than a shortcut.
                  <kbd className="text-[10px] font-mono tracking-wide text-text-muted/50 group-hover:text-text-muted">
                    {item.shortcut}
                  </kbd>
                )}
              </button>
            );
          })}
        </nav>

        {/* Collapse control mirrors the nav item geometry above it, so the rail
            reads as one column instead of a list with a stray button bolted on. */}
        <div className="p-2 border-t">
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : undefined}
            className={cn(
              "w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm text-text-muted transition-colors hover:bg-surface-sunk hover:text-text",
              collapsed && "justify-center px-0",
            )}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4 shrink-0" aria-hidden />
            ) : (
              <ChevronLeft className="h-4 w-4 shrink-0" aria-hidden />
            )}
            {!collapsed && <span className="flex-1 text-left">Collapse</span>}
          </button>
        </div>
      </aside>

      {/* Mobile drawer trigger */}
      <button
        type="button"
        className="md:hidden fixed top-3 left-3 z-50 p-2 rounded-md bg-surface border shadow-sm-signal"
        onClick={() => setMobileOpen(true)}
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main
          id="main-content"
          className="flex-1 min-w-0 px-4 md:px-6 py-4 md:py-6 max-w-[1440px] w-full mx-auto"
        >
          {children}
        </main>
      </div>

      <CommandPalette />
      <MobileTabBar />
    </div>
  );
}
