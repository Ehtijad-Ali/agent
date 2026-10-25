"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToastAction } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import {
  Check,
  X,
  Clock,
  Pencil,
  Send,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";
import { useSignalStore } from "@/stores/signal-store";
import * as api from "@/lib/api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EmptyState } from "@/components/signal/primitives";
import { InspectorAnalysis } from "./inspector-analysis";
import { InspectorReply } from "./inspector-reply";
import { InspectorSource } from "./inspector-source";
import { InspectorHistory } from "./inspector-history";
import type { Conversation, Status } from "@/lib/types";

interface InspectorProps {
  conversation: Conversation | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onAfterAction: () => void;
}


// Found by read-only discovery connectors: a person replies on the platform
// itself, then records it with "Mark posted".
const MANUAL_PLATFORMS = new Set(["reddit", "youtube"]);

export function Inspector({
  conversation,
  collapsed,
  onToggleCollapse,
  onAfterAction,
}: InspectorProps) {
  const [tab, setTab] = React.useState("analysis");
  const replyRef = React.useRef<HTMLTextAreaElement | null>(null);
  const { toast } = useToast();
  const updateConversation = useSignalStore((s) => s.updateConversation);
  const maxLength = useSignalStore((s) => s.config.voice.maxLength);

  // Reset to Analysis tab when switching conversations.
  React.useEffect(() => {
    setTab("analysis");
  }, [conversation?.id]);

  const handleVariantChange = React.useCallback(
    (index: number) => {
      if (!conversation) return;
      updateConversation({
        ...conversation,
        selectedVariant: index,
        editedReply: undefined,
        history: [
          ...conversation.history,
          {
            at: new Date().toISOString(),
            actor: "you",
            action: `Switched to variant ${index + 1}`,
          },
        ],
      });
    },
    [conversation, updateConversation],
  );

  const handleAiRedraft = React.useCallback(async () => {
    if (!conversation) return;
    try {
      const updated = await api.aiRedraft(conversation.id);
      const { conversations, setConversations } = useSignalStore.getState();
      setConversations(conversations.map((c) => (c.id === updated.id ? updated : c)));
      toast({ title: "AI rewrote the summary and drafts", duration: 2400 });
    } catch (cause) {
      toast({
        title: "AI redraft failed",
        description: cause instanceof api.ApiError ? cause.message : "Try again.",
        variant: "destructive",
      });
    }
  }, [conversation, toast]);

  const handleEditReply = React.useCallback(
    (text: string) => {
      if (!conversation) return;
      updateConversation({ ...conversation, editedReply: text });
    },
    [conversation, updateConversation],
  );

  return (
    <div className="flex flex-col h-full">
      <Header collapsed={collapsed} onToggleCollapse={onToggleCollapse} />
      <div className="flex-1 min-h-0">
        {conversation ? (
          <Tabs
            value={tab}
            onValueChange={setTab}
            className="flex h-full flex-col gap-0"
          >
            <div className="px-4 pt-2 border-b">
              <TabsList className="bg-transparent p-0 h-9 gap-1">
                <TabsTrigger value="analysis" className="text-xs">
                  Analysis
                </TabsTrigger>
                <TabsTrigger value="reply" className="text-xs">
                  Reply
                </TabsTrigger>
                <TabsTrigger value="source" className="text-xs">
                  Source
                </TabsTrigger>
                <TabsTrigger value="history" className="text-xs">
                  History
                </TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="analysis" className="flex-1 min-h-0 overflow-hidden mt-0">
              <div className="h-full overflow-y-auto">
                <InspectorAnalysis c={conversation} />
              </div>
            </TabsContent>
            <TabsContent value="reply" className="flex-1 min-h-0 overflow-hidden mt-0">
              <div className="h-full overflow-y-auto">
                <InspectorReply
                  conversation={conversation}
                  maxLength={maxLength}
                  textareaRef={replyRef}
                  onVariantChange={handleVariantChange}
                  onEditReply={handleEditReply}
                  onAiRedraft={conversation.riskFlags.length ? undefined : handleAiRedraft}
                  onToast={(msg) => toast({ title: msg, duration: 2400 })}
                />
              </div>
            </TabsContent>
            <TabsContent value="source" className="flex-1 min-h-0 overflow-hidden mt-0">
              <div className="h-full overflow-y-auto">
                <InspectorSource c={conversation} />
              </div>
            </TabsContent>
            <TabsContent value="history" className="flex-1 min-h-0 overflow-hidden mt-0">
              <div className="h-full overflow-y-auto">
                <InspectorHistory c={conversation} />
              </div>
            </TabsContent>
          </Tabs>
        ) : (
          <EmptyState
            icon={PanelRightOpen}
            title="Select a conversation to inspect"
            description="Pick a row from the list to see how it scored and what the drafted replies look like."
          />
        )}
      </div>

      {conversation && (
        <FooterActions
          conversation={conversation}
          onEdit={() => {
            setTab("reply");
            setTimeout(() => replyRef.current?.focus(), 60);
          }}
          onAfterAction={onAfterAction}
        />
      )}
    </div>
  );
}

function Header({
  collapsed,
  onToggleCollapse,
}: {
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  return (
    <div className="flex items-center justify-between h-12 px-4 border-b shrink-0">
      <h2 className="text-sm font-semibold">Inspector</h2>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        onClick={onToggleCollapse}
        aria-label={collapsed ? "Expand inspector" : "Collapse inspector"}
        aria-expanded={!collapsed}
      >
        {collapsed ? (
          <PanelRightOpen className="h-4 w-4" />
        ) : (
          <PanelRightClose className="h-4 w-4" />
        )}
      </Button>
    </div>
  );
}

function FooterActions({
  conversation,
  onEdit,
  onAfterAction,
}: {
  conversation: Conversation;
  onEdit: () => void;
  onAfterAction: () => void;
}) {
  const { toast } = useToast();
  const updateConversation = useSignalStore((s) => s.updateConversation);
  const sendReply = useSignalStore((s) => s.sendReply);
  const [sending, setSending] = React.useState(false);
  const [sendOpen, setSendOpen] = React.useState(false);
  const [preview, setPreview] = React.useState<api.ReplyPreview | null>(null);

  // Sending requires "approved" -- the server enforces this too, and refuses
  // regardless of what this component believes.
  const isApproved = conversation.status === "approved";
  const alreadySent = conversation.status === "sent";

  // Never leave a dialog armed against a conversation the operator has moved
  // away from.
  React.useEffect(() => {
    setSendOpen(false);
    setPreview(null);
  }, [conversation.id]);

  /** Ask the server what would be posted, and why it might be refused. */
  const openSendDialog = async () => {
    setPreview(null);
    setSendOpen(true);
    try {
      setPreview(await api.previewReply(conversation.id));
    } catch (cause) {
      setPreview({
        text: "",
        canSend: false,
        problems: [
          cause instanceof Error ? cause.message : "Could not reach the backend.",
        ],
      });
    }
  };

  const confirmSend = async () => {
    setSending(true);
    const result = await sendReply(conversation.id);
    setSending(false);
    setSendOpen(false);

    if (typeof result === "string") {
      // The safety check refused, or the platform did. Either way nothing was
      // posted, and the reason matters more than the failure.
      toast({
        title: "Reply not sent",
        description: result,
        variant: "destructive",
        duration: 12000,
      });
      return;
    }
    toast({
      title: "Reply posted",
      description: `Sent to ${conversation.community}. This cannot be undone.`,
      duration: 8000,
    });
  };

  /**
   * Apply a triage decision.
   *
   * ``advance`` moves the selection on to the next queued conversation, which
   * is what you want for reject/snooze. Approve deliberately stays put: it is
   * the prerequisite for sending, so jumping away would carry the Send button
   * off screen before it could be used.
   */
  const act = (status: Status, label: string, advance = true) => {
    const prev = conversation;
    const updated: Conversation = {
      ...prev,
      status,
      history: [
        ...prev.history,
        {
          at: new Date().toISOString(),
          actor: "you",
          action: `Status changed to ${status}`,
        },
      ],
    };
    updateConversation(updated);
    toast({
      title: label,
      description: `Conversation ${prev.id} ${label.toLowerCase()}`,
      duration: 6000,
      action: (
        <ToastAction
          altText="Undo"
          onClick={() => {
            updateConversation(prev);
            toast({ title: "Undone", duration: 2000 });
          }}
        >
          Undo
        </ToastAction>
      ),
    });
    if (advance) onAfterAction();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
      className="border-t bg-surface p-3 flex flex-wrap items-center gap-1.5 shrink-0"
    >
      <Button
        size="sm"
        onClick={() => act("approved", "Approved", false)}
        disabled={isApproved || alreadySent}
        className="bg-success text-white hover:bg-success/90 disabled:opacity-100 disabled:bg-success/70"
        aria-pressed={isApproved}
      >
        <Check className="h-3.5 w-3.5" />
        {isApproved ? "Approved" : "Approve"}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={() => act("rejected", "Rejected")}
        disabled={conversation.status === "rejected" || alreadySent}
        aria-pressed={conversation.status === "rejected"}
      >
        <X className="h-3.5 w-3.5" />
        {conversation.status === "rejected" ? "Rejected" : "Reject"}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => act("snoozed", "Snoozed 24h")}
        disabled={conversation.status === "snoozed" || alreadySent}
        aria-pressed={conversation.status === "snoozed"}
      >
        <Clock className="h-3.5 w-3.5" />
        {conversation.status === "snoozed" ? "Snoozed" : "Snooze 24h"}
      </Button>
      <div className="flex-1" />
      <Button variant="ghost" size="sm" onClick={onEdit}>
        <Pencil className="h-3.5 w-3.5" />
        Edit
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => act("manually_posted", "Marked manually posted")}
        disabled={conversation.status === "manually_posted" || alreadySent}
        aria-pressed={conversation.status === "manually_posted"}
      >
        <Pencil className="h-3.5 w-3.5" />
        {conversation.status === "manually_posted" ? "Posted" : "Mark posted"}
      </Button>
      {MANUAL_PLATFORMS.has(conversation.platform) ? (
        conversation.sourceUrl ? (
          <Button size="sm" variant="outline" asChild title="Open the original post to reply there, then click Mark posted">
            <a href={conversation.sourceUrl} target="_blank" rel="noreferrer">
              <Send className="h-3.5 w-3.5" /> Reply on {conversation.platform === "youtube" ? "YouTube" : "Reddit"}
            </a>
          </Button>
        ) : null
      ) : (
      <Button
        size="sm"
        variant="outline"
        onClick={openSendDialog}
        disabled={!isApproved || sending}
        title={
          alreadySent
            ? "Already replied. One reply per person, ever."
            : isApproved
              ? "Post this reply to the platform"
              : "Approve the conversation first"
        }
        aria-label="Send reply to the platform"
      >
        <Send className="h-3.5 w-3.5" />
        {alreadySent ? "Replied" : sending ? "Sending…" : "Send reply"}
      </Button>
      )}

      <AlertDialog open={sendOpen} onOpenChange={setSendOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Post this reply to {conversation.platform}?
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                <p>
                  It will appear publicly in{" "}
                  <span className="font-medium text-text">
                    {conversation.community}
                  </span>{" "}
                  as a reply to {conversation.authorPseudonym}. This cannot be
                  undone, and no further reply to this person will ever be
                  allowed.
                </p>

                {preview === null ? (
                  <p className="text-text-muted">Checking…</p>
                ) : (
                  <>
                    <div className="rounded-md border bg-surface-sunk p-2.5 text-sm text-text whitespace-pre-wrap">
                      {preview.text || "(nothing to send)"}
                    </div>
                    {preview.problems.length > 0 && (
                      <div className="rounded-md border border-destructive/40 p-2.5">
                        <p className="font-medium text-destructive">
                          Blocked by the safety check:
                        </p>
                        <ul className="mt-1 list-disc pl-4 space-y-0.5">
                          {preview.problems.map((problem) => (
                            <li key={problem}>{problem}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={sending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                // Keep the dialog open on refusal so the reasons stay readable.
                event.preventDefault();
                void confirmSend();
              }}
              disabled={sending || !preview?.canSend}
            >
              {sending ? "Sending…" : "Post reply"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </motion.div>
  );
}
