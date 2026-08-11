"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useSignalStore } from "@/stores/signal-store";
import { useToast } from "@/hooks/use-toast";
import type { Conversation, Status } from "@/lib/types";
import { TriageCard } from "@/components/triage/triage-card";
import { TriageHintBar } from "@/components/triage/triage-hint-bar";
import { TriageProgress } from "@/components/triage/triage-progress";
import {
  TriageEmpty,
  type TriageSessionCounts,
} from "@/components/triage/triage-empty";

type DecisionAction = "approve" | "reject" | "snooze";
interface Decision {
  id: string;
  action: DecisionAction;
  prev: Conversation;
}

const ACTION_META: Record<DecisionAction, { status: Status; label: string }> = {
  approve: { status: "approved", label: "Approved" },
  reject: { status: "rejected", label: "Rejected" },
  snooze: { status: "snoozed", label: "Snoozed 24h" },
};

const KEY_TO_ACTION: Record<string, DecisionAction> = {
  a: "approve",
  r: "reject",
  s: "snooze",
};

const EXIT_DURATION = 0.18; // 180ms — within the 150–200ms spec range

function historyEntry(action: string) {
  return { at: new Date().toISOString(), actor: "you", action };
}

/**
 * TriageView — distraction-free card stack of unreviewed conversations,
 * highest score first. One card centered, next two peek behind.
 * Keyboard: A approve · R reject · S snooze · E edit · ← → variants ·
 * Z undo · Esc exit. Mobile: drag the top card left/right.
 */
export function TriageView() {
  const conversations = useSignalStore((s) => s.conversations);
  const updateConversation = useSignalStore((s) => s.updateConversation);
  const setCurrentView = useSignalStore((s) => s.setCurrentView);
  const maxLength = useSignalStore((s) => s.config.voice.maxLength);
  const { toast } = useToast();
  const reducedMotion = useReducedMotion();

  const queue = React.useMemo(
    () =>
      conversations
        .filter((c) => c.status === "new" || c.status === "awaiting")
        .sort((a, b) => b.score - a.score),
    [conversations],
  );

  // Capture the queue length once after hydration settles.
  const [totalAtStart, setTotalAtStart] = React.useState(0);
  const capturedRef = React.useRef(false);
  React.useEffect(() => {
    if (capturedRef.current) return;
    capturedRef.current = true;
    const fresh = useSignalStore
      .getState()
      .conversations.filter(
        (c) => c.status === "new" || c.status === "awaiting",
      );
    setTotalAtStart(fresh.length);
  }, []);

  const decisionsRef = React.useRef<Decision[]>([]);
  const [sessionCounts, setSessionCounts] = React.useState<TriageSessionCounts>({
    approved: 0,
    rejected: 0,
    snoozed: 0,
  });

  const exitDirRef = React.useRef<DecisionAction>("snooze");
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const noopRef = React.useRef<HTMLTextAreaElement | null>(null);

  // Always-fresh ref so the global keydown handler sees the latest top card.
  const currentConvRef = React.useRef<Conversation | null>(null);
  React.useEffect(() => {
    currentConvRef.current = queue[0] ?? null;
  });

  const decide = React.useCallback(
    (conv: Conversation | null, action: DecisionAction) => {
      if (!conv) return;
      const meta = ACTION_META[action];
      exitDirRef.current = action;
      updateConversation({
        ...conv,
        status: meta.status,
        history: [
          ...conv.history,
          historyEntry(`Status changed to ${meta.status}`),
        ],
      });
      decisionsRef.current = [
        ...decisionsRef.current,
        { id: conv.id, action, prev: conv },
      ];
      setSessionCounts((prev) => ({ ...prev, [action]: prev[action] + 1 }));
      toast({ title: meta.label, description: `Conversation ${conv.id}`, duration: 2400 });
    },
    [updateConversation, toast],
  );

  const undo = React.useCallback(() => {
    const stack = decisionsRef.current;
    if (stack.length === 0) {
      toast({ title: "Nothing to undo", duration: 1800 });
      return;
    }
    const last = stack[stack.length - 1];
    decisionsRef.current = stack.slice(0, -1);
    updateConversation(last.prev);
    setSessionCounts((c) => ({ ...c, [last.action]: Math.max(0, c[last.action] - 1) }));
    toast({ title: `Undid ${ACTION_META[last.action].label}`, description: `Conversation ${last.id}`, duration: 2400 });
  }, [updateConversation, toast]);

  const changeVariant = React.useCallback(
    (conv: Conversation | null, delta: number) => {
      if (!conv || conv.replyVariants.length === 0) return;
      const n = conv.replyVariants.length;
      const next = (conv.selectedVariant + delta + n) % n;
      updateConversation({
        ...conv,
        selectedVariant: next,
        editedReply: undefined,
        history: [
          ...conv.history,
          historyEntry(`Switched to variant ${next + 1}`),
        ],
      });
    },
    [updateConversation],
  );

  const focusTextarea = React.useCallback(() => {
    textareaRef.current?.focus();
  }, []);

  // Latest callbacks for the global keydown handler.
  const actionsRef = React.useRef({ decide, undo, changeVariant, focusTextarea, setCurrentView });
  React.useEffect(() => {
    actionsRef.current = { decide, undo, changeVariant, focusTextarea, setCurrentView };
  });

  // Global keyboard shortcuts — captured on window, reads latest via refs.
  React.useEffect(() => {
    function handler(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      const editing = t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || (t?.isContentEditable ?? false);
      if (editing) {
        if (e.key === "Escape") { e.preventDefault(); t?.blur(); }
        return;
      }
      const k = e.key.toLowerCase();
      const a = actionsRef.current;
      const cur = currentConvRef.current;
      const action = KEY_TO_ACTION[k];
      if (action) {
        e.preventDefault();
        a.decide(cur, action);
      } else if (k === "e") {
        e.preventDefault();
        a.focusTextarea();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        a.changeVariant(cur, 1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        a.changeVariant(cur, -1);
      } else if (k === "z") {
        e.preventDefault();
        a.undo();
      } else if (k === "escape") {
        e.preventDefault();
        a.setCurrentView("inbox");
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const cardVariants = React.useMemo(
    () => ({
      enter: reducedMotion ? { opacity: 0 } : { y: 40, opacity: 0, scale: 1 },
      center: (depth: number) =>
        reducedMotion
          ? { opacity: depth === 0 ? 1 : 1 - depth * 0.3, y: 0, scale: 1 }
          : {
              y: depth === 0 ? 0 : depth * 12,
              opacity: depth === 0 ? 1 : 1 - depth * 0.3,
              scale: depth === 0 ? 1 : 1 - depth * 0.05,
            },
      exit: () => {
        if (reducedMotion) return { opacity: 0 };
        const dir = exitDirRef.current;
        if (dir === "approve")
          return { x: 200, opacity: 0, boxShadow: "0 0 50px 0px var(--primary)" };
        if (dir === "reject")
          return { x: -200, opacity: 0, boxShadow: "0 0 50px 0px var(--risk)" };
        return { y: -40, opacity: 0 };
      },
    }),
    [reducedMotion],
  );

  const cleared = Math.min(totalAtStart - queue.length, totalAtStart);
  const isEmpty = queue.length === 0;
  const visible = queue.slice(0, 3);

  return (
    <div
      className="flex flex-col bg-canvas border rounded-xl overflow-hidden shadow-sm-signal"
      style={{ height: "calc(100vh - 7rem)" }}
    >
      <TriageProgress cleared={cleared} total={totalAtStart} />

      <div className="flex-1 min-h-0 relative">
        {isEmpty ? (
          <div className="h-full flex items-center justify-center overflow-y-auto">
            <TriageEmpty
              counts={sessionCounts}
              reviewedTotal={totalAtStart}
              onBackToInbox={() => setCurrentView("inbox")}
            />
          </div>
        ) : (
          <div className="relative h-full px-3 sm:px-4 py-3 sm:py-4">
            <AnimatePresence initial>
              {visible.map((c, i) => (
                <motion.div
                  key={c.id}
                  custom={i}
                  variants={cardVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={{ duration: EXIT_DURATION, ease: "easeOut" }}
                  style={{
                    position: "absolute",
                    inset: 0,
                    zIndex: 10 - i,
                    pointerEvents: i === 0 ? "auto" : "none",
                  }}
                  drag={i === 0 && !reducedMotion ? true : false}
                  dragDirectionLock
                  dragSnapToOrigin
                  dragElastic={0.6}
                  onDragEnd={(_, info) => {
                    if (info.offset.x > 100) decide(c, "approve");
                    else if (info.offset.x < -100) decide(c, "reject");
                  }}
                >
                  <TriageCard
                    conversation={c}
                    maxLength={maxLength}
                    textareaRef={i === 0 ? textareaRef : noopRef}
                    onApprove={() => decide(c, "approve")}
                    onReject={() => decide(c, "reject")}
                    onSnooze={() => decide(c, "snooze")}
                    onEdit={focusTextarea}
                    onVariantChange={(delta) => changeVariant(c, delta)}
                    onEditReply={(text) =>
                      updateConversation({ ...c, editedReply: text })
                    }
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      <TriageHintBar />
    </div>
  );
}
