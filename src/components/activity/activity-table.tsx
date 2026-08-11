"use client";

import * as React from "react";
import { Bot, User, Clipboard, Check, ArrowRight } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableCaption,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/signal/primitives";
import { useToast } from "@/hooks/use-toast";
import type { ActivityEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

/* ============================================================
   Activity table — the audit log.
   Columns: Timestamp (relative + absolute on hover) · Actor
   (badge with icon) · Action · Item (mono, truncated, copy
   button) · Before → After (diff with before muted and after
   in primary, arrow between).
   ============================================================ */

function relativeTime(iso: string, now: number): string {
  const then = +new Date(iso);
  const diff = Math.max(0, now - then);
  const sec = Math.floor(diff / 1000);
  if (sec < 5) return "just now";
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  const month = Math.floor(day / 30);
  if (month < 12) return `${month}mo ago`;
  return `${Math.floor(month / 12)}y ago`;
}

function absoluteTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function truncate(text: string, max = 40): string {
  if (text.length <= max) return text;
  return text.slice(0, max - 1) + "…";
}

interface ActivityTableProps {
  rows: ActivityEntry[];
}

export function ActivityTable({ rows }: ActivityTableProps) {
  const [now, setNow] = React.useState(() => Date.now());

  // Refresh "x ago" labels every 30s while the view is mounted.
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(id);
  }, []);

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={ArrowRight}
        title="No activity yet"
        description="Anything you do in Signal shows up here."
      />
    );
  }

  return (
    <div className="rounded-md border max-h-[calc(100vh-22rem)] overflow-y-auto">
      <Table>
        <TableCaption className="sr-only">
          Audit log of actions taken in the Signal app, most recent first.
        </TableCaption>
        <TableHeader className="sticky top-0 bg-surface z-10">
          <TableRow>
            <TableHead className="w-32">Timestamp</TableHead>
            <TableHead className="w-28">Actor</TableHead>
            <TableHead>Action</TableHead>
            <TableHead className="w-56">Item</TableHead>
            <TableHead className="w-72">Before → After</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <ActivityRow key={r.id} row={r} now={now} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function ActivityRow({ row, now }: { row: ActivityEntry; now: number }) {
  const isSystem = row.actor === "system";
  const actorLabel = isSystem ? "System" : "You";
  return (
    <TableRow>
      <TableCell className="text-xs">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                className="text-text-muted tabular-nums cursor-help"
                aria-label={`Timestamp ${absoluteTime(row.timestamp)}`}
              >
                {relativeTime(row.timestamp, now)}
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="font-mono text-xs">
              {absoluteTime(row.timestamp)}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </TableCell>

      <TableCell>
        <Badge
          variant="outline"
          className={cn(
            "gap-1 font-normal",
            isSystem
              ? "border-border text-text-muted bg-surface-sunk"
              : "border-primary/30 text-primary bg-primary-soft",
          )}
          aria-label={`Actor: ${actorLabel}`}
        >
          {isSystem ? (
            <Bot className="h-3 w-3" aria-hidden />
          ) : (
            <User className="h-3 w-3" aria-hidden />
          )}
          <span>{actorLabel}</span>
        </Badge>
      </TableCell>

      <TableCell className="text-sm text-text">{row.action}</TableCell>

      <TableCell>
        <ItemCell item={row.item} />
      </TableCell>

      <TableCell>
        <BeforeAfter before={row.before} after={row.after} />
      </TableCell>
    </TableRow>
  );
}

function ItemCell({ item }: { item: string }) {
  const { toast } = useToast();
  const [copied, setCopied] = React.useState(false);

  const handleCopy = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(item);
      setCopied(true);
      toast({ title: "Copied item ID", duration: 1600 });
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast({ title: "Copy failed", duration: 1600 });
    }
  }, [item, toast]);

  if (item === "—" || item === "") {
    return <span className="text-text-muted text-xs">—</span>;
  }

  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="font-mono text-xs text-text truncate max-w-[180px]">
              {truncate(item, 28)}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="font-mono text-xs max-w-xs">
            {item}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 shrink-0"
        onClick={handleCopy}
        aria-label={`Copy item ID ${item} to clipboard`}
      >
        {copied ? (
          <Check className="h-3 w-3 text-success" />
        ) : (
          <Clipboard className="h-3 w-3 text-text-muted" />
        )}
      </Button>
    </div>
  );
}

function BeforeAfter({
  before,
  after,
}: {
  before?: string;
  after?: string;
}) {
  if (before === undefined && after === undefined) {
    return <span className="text-text-muted text-xs">—</span>;
  }
  return (
    <div className="flex items-center gap-2 text-xs min-w-0">
      <span
        className="text-text-muted truncate max-w-[120px]"
        aria-label="Before"
        title={before}
      >
        {before && before !== "" ? truncate(before, 24) : "—"}
      </span>
      <ArrowRight className="h-3 w-3 text-text-muted shrink-0" aria-hidden />
      <span
        className="text-primary font-medium truncate max-w-[120px]"
        aria-label="After"
        title={after}
      >
        {after && after !== "" ? truncate(after, 24) : "—"}
      </span>
    </div>
  );
}
