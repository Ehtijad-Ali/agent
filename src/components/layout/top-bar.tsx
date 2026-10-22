"use client";

import * as React from "react";
import { logout } from "@/lib/api";
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
  LogOut,
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
  const startScan = useSignalStore((s) => s.runScan);
  const scanning = useSignalStore((s) => s.scanning);
  const platforms = useSignalStore((s) => s.platforms);
  const lastScanAt = useSignalStore((s) => s.lastScanAt);
  const queueCount = useSignalStore(
    (s) =>
      s.conversations.filter(
        (c) => c.status === "new" || c.status === "awaiting",
      ).length,
  );
  const { toast } = useToast();

  const connected = platforms.filter((p) => p.status === "connected");

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

  async function runScan() {
    toast({
      title: "Scan started",
      description: connected.length
        ? `Polling ${connected.map((p) => p.platform).join(", ")}.`
        : "No platform is connected yet.",
    });

    const result = await startScan();
    if (!result) {
      toast({
        title: "Scan failed",
        description:
          useSignalStore.getState().error ?? "The backend did not respond.",
        variant: "destructive",
      });
      return;
    }
    if (result.error) {
      toast({
        title: "Scan could not run",
        description: result.error,
        variant: "destructive",
      });
      return;
    }

    // Report what actually happened. "Examined but nothing new" is the normal
    // result of polling a quiet channel and must not read as a failure.
    const failed = result.platforms.filter((p) => p.error);
    toast({
      title: result.discovered
        ? `Found ${result.discovered} new conversation${result.discovered === 1 ? "" : "s"}`
        : "No new conversations",
      description: [
        `Examined ${result.examined} message${result.examined === 1 ? "" : "s"}.`,
        failed.length
          ? `${failed.map((p) => `${p.platform}: ${p.error}`).join("; ")}`
          : null,
      ]
        .filter(Boolean)
        .join(" "),
      variant: failed.length ? "destructive" : undefined,
    });
  }

  function relativeTime(iso: string | null): string {
    if (!iso) return "no scan yet";
    const seconds = Math.max(0, Math.round((Date.now() - +new Date(iso)) / 1000));
    if (seconds < 60) return "just now";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    return `${Math.round(minutes / 60)}h ago`;
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
              aria-label={
                scanning
                  ? "Scan status: running"
                  : `Scan status: idle, last scan ${relativeTime(lastScanAt)}`
              }
            >
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  scanning
                    ? "bg-warning animate-pulse"
                    : connected.length
                      ? "bg-success"
                      : "bg-text-muted",
                )}
                aria-hidden
              />
              <span>
                {scanning ? "Scanning…" : `Last scan ${relativeTime(lastScanAt)}`}
              </span>
            </span>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {connected.length
              ? `Listening across ${connected.length} platform${connected.length === 1 ? "" : "s"} · ${queueCount} conversation${queueCount === 1 ? "" : "s"} in queue`
              : "No platform connected. Add a bot token in backend/.env."}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <Button
        size="sm"
        onClick={runScan}
        disabled={scanning}
        className="gap-1.5"
        aria-label="Run scan now"
      >
        <Play className="h-3.5 w-3.5" aria-hidden />
        <span className="hidden sm:inline">
          {scanning ? "Scanning…" : "Run scan"}
        </span>
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

      <SignOutButton />

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

/** Ends the session and returns to the sign-in screen. */
function SignOutButton() {
  const [busy, setBusy] = React.useState(false);
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            disabled={busy}
            aria-label="Sign out"
            onClick={async () => {
              setBusy(true);
              try {
                await logout();
              } finally {
                // Navigate even if the request failed: the cookie may already
                // be gone, and stranding the user on a dead session is worse
                // than an extra trip through the login screen.
                window.location.href = "/login";
              }
            }}
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">Sign out</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
