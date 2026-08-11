"use client";

import * as React from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "signal.triage.hintsHidden";

const HINTS = [
  { kbd: "A", label: "approve" },
  { kbd: "R", label: "reject" },
  { kbd: "E", label: "edit" },
  { kbd: "S", label: "snooze" },
  { kbd: "← →", label: "variants" },
  { kbd: "Z", label: "undo" },
  { kbd: "Esc", label: "exit" },
] as const;

/**
 * TriageHintBar — floating row of keyboard-shortcut chips at the bottom
 * of the triage screen. Dismissible; the hidden state is persisted in
 * localStorage so it stays dismissed across sessions.
 *
 * On touch screens the chip row is replaced by a single "swipe ↔ to decide"
 * hint since the keyboard shortcuts are desktop-only.
 */
export function TriageHintBar() {
  const [hidden, setHidden] = React.useState(false);

  React.useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "true") setHidden(true);
    } catch {
      // ignore storage failures (private mode etc.)
    }
  }, []);

  const dismiss = React.useCallback(() => {
    setHidden(true);
    try {
      window.localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      // ignore
    }
  }, []);

  if (hidden) return null;

  return (
    <div
      className="fixed bottom-20 md:bottom-4 inset-x-0 z-20 flex justify-center pointer-events-none px-4"
      role="region"
      aria-label="Keyboard shortcuts"
    >
      <div
        className={cn(
          "pointer-events-auto inline-flex items-center gap-2.5 rounded-pill border bg-surface px-3 py-2 shadow-md-signal max-w-full",
        )}
      >
        <div className="hidden sm:flex items-center gap-1.5 text-xs text-text-muted">
          {HINTS.map((h, i) => (
            <React.Fragment key={h.kbd}>
              {i > 0 && (
                <span className="text-text-muted/50" aria-hidden>
                  ·
                </span>
              )}
              <span className="inline-flex items-center gap-1 whitespace-nowrap">
                <kbd className="font-mono text-[10px] px-1.5 py-0.5 rounded border bg-surface-sunk text-text">
                  {h.kbd}
                </kbd>
                <span>{h.label}</span>
              </span>
            </React.Fragment>
          ))}
        </div>
        <div className="flex sm:hidden items-center gap-1 text-xs text-text-muted">
          <kbd className="font-mono text-[10px] px-1.5 py-0.5 rounded border bg-surface-sunk text-text">
            tap
          </kbd>
          <span>swipe ↔ to decide</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          onClick={dismiss}
          aria-label="Hide keyboard hints"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
