"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { ToastAction } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { useSignalStore } from "@/stores/signal-store";
import { Check, X, Clock, Download } from "lucide-react";
import type { Conversation, Status } from "@/lib/types";

interface BulkBarProps {
  selected: Conversation[];
  onClear: () => void;
  onAfterAction: () => void;
}

export function BulkActionBar({
  selected,
  onClear,
  onAfterAction,
}: BulkBarProps) {
  const { toast } = useToast();
  const count = selected.length;

  const apply = (status: Status, label: string) => {
    if (count === 0) return;
    const prev = selected.map((c) => ({ ...c }));
    const update = useSignalStore.getState().updateConversation;
    for (const c of prev) {
      update({
        ...c,
        status,
        history: [
          ...c.history,
          {
            at: new Date().toISOString(),
            actor: "you",
            action: `Bulk ${label} (${count} items)`,
          },
        ],
      });
    }
    toast({
      title: `${label} ${count} conversation${count === 1 ? "" : "s"}`,
      duration: 6000,
      action: (
        <ToastAction
          altText="Undo"
          onClick={() => {
            for (const c of prev) update(c);
            toast({ title: "Bulk action undone", duration: 2000 });
          }}
        >
          Undo
        </ToastAction>
      ),
    });
    onAfterAction();
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(selected, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `signal-conversations-${selected.length}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast({
      title: `Exported ${count} conversation${count === 1 ? "" : "s"}`,
      duration: 2400,
    });
  };

  return (
    <AnimatePresence>
      {count > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 24 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 rounded-full border bg-surface px-3 py-2 shadow-lg-signal"
          role="toolbar"
          aria-label="Bulk actions"
        >
          <span className="px-2 text-xs font-medium text-text">
            <span className="font-mono tabular-nums font-semibold">
              {count}
            </span>{" "}
            selected
          </span>
          <div className="h-5 w-px bg-border" aria-hidden />
          <Button
            size="sm"
            className="h-7 rounded-full bg-success text-white hover:bg-success/90"
            onClick={() => apply("approved", "Approved")}
          >
            <Check className="h-3.5 w-3.5" />
            Approve {count}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 rounded-full"
            onClick={() => apply("rejected", "Rejected")}
          >
            <X className="h-3.5 w-3.5" />
            Reject
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 rounded-full"
            onClick={() => apply("snoozed", "Snoozed")}
          >
            <Clock className="h-3.5 w-3.5" />
            Snooze
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 rounded-full"
            onClick={handleExport}
          >
            <Download className="h-3.5 w-3.5" />
            Export
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 rounded-full text-text-muted"
            onClick={onClear}
            aria-label="Clear selection"
          >
            Clear
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
