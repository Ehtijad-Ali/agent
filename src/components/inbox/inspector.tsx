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

  const act = (status: Status, label: string) => {
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
    onAfterAction();
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
        onClick={() => act("approved", "Approved")}
        className="bg-success text-white hover:bg-success/90"
      >
        <Check className="h-3.5 w-3.5" />
        Approve
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={() => act("rejected", "Rejected")}
      >
        <X className="h-3.5 w-3.5" />
        Reject
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => act("snoozed", "Snoozed 24h")}
      >
        <Clock className="h-3.5 w-3.5" />
        Snooze 24h
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
      >
        <Send className="h-3.5 w-3.5" />
        Mark posted
      </Button>
    </motion.div>
  );
}
