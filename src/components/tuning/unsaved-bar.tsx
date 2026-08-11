"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Check, RotateCcw } from "lucide-react";

/**
 * UnsavedBar — sticky bottom-of-left-pane action bar shown only when the
 * draft diverges from the committed config. Save commits + fires a toast;
 * Discard throws the draft away. Both restore the preview samples to the
 * committed config (handled by the store).
 */
export function UnsavedBar() {
  const hasUnsavedChanges = useSignalStore((s) => s.hasUnsavedChanges);
  const commitConfig = useSignalStore((s) => s.commitConfig);
  const discardConfig = useSignalStore((s) => s.discardConfig);
  const { toast } = useToast();

  // Animate in/out — render null when there's nothing to show so the bar
  // doesn't reserve space below the accordion.
  if (!hasUnsavedChanges) return null;

  function handleSave() {
    commitConfig();
    toast({
      title: "Configuration saved",
      description: "Preview samples re-scored against your new config.",
      duration: 2600,
    });
  }

  return (
    <div className="sticky bottom-4 z-20">
      <div
        className="flex items-center justify-between gap-3 rounded-lg border bg-surface shadow-lg-signal px-4 py-3"
        role="region"
        aria-label="Unsaved changes"
      >
        <span className="text-sm text-text">
          You have unsaved changes
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={discardConfig}
            aria-label="Discard draft"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            Discard
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            aria-label="Save configuration"
          >
            <Check className="h-3.5 w-3.5" aria-hidden />
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}
