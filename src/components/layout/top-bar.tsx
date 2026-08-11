"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { useSignalStore } from "@/stores/signal-store";
import {
  Search,
  Moon,
  Sun,
  Radar,
  Play,
  HelpCircle,
  PanelLeftOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "next-themes";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useToast } from "@/hooks/use-toast";

/**
 * TopBar — global search, ⌘K palette trigger, theme toggle, scan status,
 * "Run scan" button, help menu.
 */
export function TopBar() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const setCurrentView = useSignalStore((s) => s.setCurrentView);
  const { toast } = useToast();

  React.useEffect(() => setMounted(true), []);

  // Open command palette on ⌘K / Ctrl+K
  React.useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Listen for a custom event from CommandPalette to close it
  React.useEffect(() => {
    function close() {
      setPaletteOpen(false);
    }
    window.addEventListener("signal:close-palette", close);
    return () => window.removeEventListener("signal:close-palette", close);
  }, []);

  function runScan() {
    toast({
      title: "Scan started",
      description: "Listening across Discord, Telegram, Facebook, and Reddit.",
    });
    setTimeout(() => {
      toast({
        title: "Scan complete",
        description: "Found 4 new conversations in the last 5 minutes.",
      });
    }, 1800);
  }

  return (
    <header
      className="sticky top-0 z-30 h-14 border-b bg-surface/95 backdrop-blur flex items-center gap-3 px-4 md:px-6"
      role="banner"
    >
      <div className="flex items-center gap-2 md:hidden">
        <div className="w-8 h-8 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
          <Radar className="h-4 w-4" />
        </div>
      </div>

      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        className="flex items-center gap-2 h-9 px-3 rounded-md border bg-surface-sunk text-text-muted text-sm hover:bg-surface-sunk/70 hover:text-text transition-colors w-full max-w-md"
        aria-label="Open command palette"
      >
        <Search className="h-4 w-4" aria-hidden />
        <span className="flex-1 text-left">Search conversations, jump to view…</span>
        <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded border bg-surface text-text-muted">
          ⌘K
        </kbd>
      </button>

      <div className="flex-1" />

      {/* Scan status chip */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className="hidden md:inline-flex items-center gap-1.5 text-xs text-text-muted px-2.5 py-1 rounded-pill border"
              role="status"
              aria-label="Scan status: idle, last scan 4 minutes ago"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-success" aria-hidden />
              <span>Last scan 4m ago</span>
            </span>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            Listening across 4 platforms · 60 conversations in queue
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <Button
        size="sm"
        onClick={runScan}
        className="gap-1.5"
        aria-label="Run scan now"
      >
        <Play className="h-3.5 w-3.5" aria-hidden />
        <span className="hidden sm:inline">Run scan</span>
      </Button>

      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={() =>
                setTheme(theme === "dark" ? "light" : "dark")
              }
              aria-label="Toggle theme"
            >
              {mounted && theme === "dark" ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Toggle theme</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setCurrentView("safety")}
              aria-label="Open Safety & compliance"
            >
              <HelpCircle className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Safety &amp; help</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {paletteOpen && (
        <PaletteContainer onClose={() => setPaletteOpen(false)} />
      )}
    </header>
  );
}

/** Wrapper so the palette can mount on demand. */
function PaletteContainer({ onClose }: { onClose: () => void }) {
  // Defer to CommandPalette which handles its own visibility via portal.
  React.useEffect(() => {
    // Trigger the global palette open event
    window.dispatchEvent(new CustomEvent("signal:open-palette"));
    onClose();
  }, [onClose]);
  return null;
}
