"use client";

import * as React from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableCaption,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { RiskPill, EmptyState, PlatformBadge } from "@/components/signal/primitives";
import { ReadonlyInspector } from "@/components/safety/readonly-inspector";
import type { Conversation, RiskFlag } from "@/lib/types";
import { ShieldCheck, Eye } from "lucide-react";

/* ============================================================
   Blocked items — guardrail #2/#3/#4 audit surface.
   Tabbed table of blocked / risk-flagged conversations. The rows
   are auditable but never repliable — only a "View" button that
   opens a read-only inspector dialog.
   ============================================================ */

type BlockedTab = "all" | "underage" | "real_money" | "spam" | "other";

const TABS: { id: BlockedTab; label: string }[] = [
  { id: "all", label: "All" },
  { id: "underage", label: "Underage" },
  { id: "real_money", label: "Real money" },
  { id: "spam", label: "Spam" },
  { id: "other", label: "Other" },
];

function matchesTab(c: Conversation, tab: BlockedTab): boolean {
  if (tab === "all") return true;
  if (tab === "underage") return c.riskFlags.includes("underage");
  if (tab === "real_money") return c.riskFlags.includes("real_money");
  if (tab === "spam") return c.riskFlags.includes("spam");
  // "other" — blocked items that don't fall into the three auto-bins.
  return (
    !c.riskFlags.includes("underage") &&
    !c.riskFlags.includes("real_money") &&
    !c.riskFlags.includes("spam") &&
    c.riskFlags.length > 0
  );
}

function primaryRisk(flags: RiskFlag[]): RiskFlag {
  if (flags.includes("underage")) return "underage";
  if (flags.includes("real_money")) return "real_money";
  if (flags.includes("spam")) return "spam";
  return flags[0];
}

function excerpt(text: string, max = 80): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (oneLine.length <= max) return oneLine;
  return oneLine.slice(0, max - 1) + "…";
}

function formatDay(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

interface BlockedItemsProps {
  conversations: Conversation[];
}

export function BlockedItems({ conversations }: BlockedItemsProps) {
  const [tab, setTab] = React.useState<BlockedTab>("all");
  const [viewId, setViewId] = React.useState<string | null>(null);

  const blocked = React.useMemo(
    () =>
      conversations.filter(
        (c) => c.status === "blocked" || c.riskFlags.length > 0,
      ),
    [conversations],
  );

  const filtered = React.useMemo(
    () => blocked.filter((c) => matchesTab(c, tab)),
    [blocked, tab],
  );

  const selected = React.useMemo(
    () => filtered.find((c) => c.id === viewId) ?? null,
    [filtered, viewId],
  );

  const tabCounts = React.useMemo(() => {
    const c: Record<BlockedTab, number> = {
      all: blocked.length,
      underage: 0,
      real_money: 0,
      spam: 0,
      other: 0,
    };
    for (const conv of blocked) {
      c.underage += matchesTab(conv, "underage") ? 1 : 0;
      c.real_money += matchesTab(conv, "real_money") ? 1 : 0;
      c.spam += matchesTab(conv, "spam") ? 1 : 0;
      c.other += matchesTab(conv, "other") ? 1 : 0;
    }
    return c;
  }, [blocked]);

  return (
    <Card id="blocked-items" className="scroll-mt-24 py-5">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Blocked items</CardTitle>
        <CardDescription>
          Caught by a safety rule. You can read these for audit, but there is no
          Approve action.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={tab} onValueChange={(v) => setTab(v as BlockedTab)}>
          <TabsList className="mb-3 h-8">
            {TABS.map((t) => (
              <TabsTrigger key={t.id} value={t.id} className="text-xs">
                {t.label}
                <Badge
                  variant="secondary"
                  className="ml-1.5 px-1.5 py-0 text-[10px] tabular-nums"
                >
                  {tabCounts[t.id]}
                </Badge>
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value={tab} className="mt-0">
            {filtered.length === 0 ? (
              <EmptyState
                icon={ShieldCheck}
                title="No blocked items"
                description="Nothing has tripped a safety rule yet."
              />
            ) : (
              <div className="rounded-md border max-h-[420px] overflow-y-auto">
                <Table>
                  <TableCaption className="sr-only">
                    Blocked conversations, caught by safety rules. Read-only.
                  </TableCaption>
                  <TableHeader className="sticky top-0 bg-surface z-10">
                    <TableRow>
                      <TableHead className="w-24">ID</TableHead>
                      <TableHead className="w-28">Platform</TableHead>
                      <TableHead>Message</TableHead>
                      <TableHead className="w-36">Risk flag</TableHead>
                      <TableHead className="w-64">Reason</TableHead>
                      <TableHead className="w-28">Date</TableHead>
                      <TableHead className="w-16 text-right">
                        <span className="sr-only">Actions</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filtered.map((c) => (
                      <BlockedRow
                        key={c.id}
                        conversation={c}
                        onView={() => setViewId(c.id)}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>

      <ReadonlyInspector
        conversation={selected}
        flag={selected ? primaryRisk(selected.riskFlags) : null}
        open={!!selected}
        onOpenChange={(o) => {
          if (!o) setViewId(null);
        }}
      />
    </Card>
  );
}

function BlockedRow({
  conversation,
  onView,
}: {
  conversation: Conversation;
  onView: () => void;
}) {
  const flag = primaryRisk(conversation.riskFlags);
  return (
    <TableRow>
      <TableCell className="font-mono text-xs text-text-muted">
        {conversation.id}
      </TableCell>
      <TableCell>
        <PlatformBadge platform={conversation.platform} />
      </TableCell>
      <TableCell className="max-w-xs">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="block truncate text-xs text-text">
                {excerpt(conversation.message)}
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-md">
              <p className="text-xs">{conversation.message}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </TableCell>
      <TableCell>
        <RiskPill flag={flag} />
      </TableCell>
      <TableCell className="text-xs text-text-muted">
        {conversation.summary}
      </TableCell>
      <TableCell className="text-xs text-text-muted tabular-nums">
        {formatDay(conversation.postedAt)}
      </TableCell>
      <TableCell className="text-right">
        <Button
          variant="ghost"
          size="sm"
          onClick={onView}
          aria-label={`View blocked item ${conversation.id} read-only`}
        >
          <Eye className="h-3.5 w-3.5" />
          View
        </Button>
      </TableCell>
    </TableRow>
  );
}
