"use client";

import * as React from "react";
import { GitCompareArrows } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { IntentPill, PlatformBadge } from "@/components/signal/primitives";
import { useSignalStore } from "@/stores/signal-store";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/lib/types";

/**
 * CompareToQueue — toggle that reveals a dropdown of every conversation in
 * the store and renders a side-by-side mini comparison: this message's
 * score vs the queue item's score, with delta.
 */
export function CompareToQueue({
  playgroundScore,
  playgroundIntent,
}: {
  playgroundScore: number;
  playgroundIntent: Conversation["intent"];
}) {
  const [enabled, setEnabled] = React.useState(false);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const conversations = useSignalStore((s) => s.conversations);

  const selected = React.useMemo(
    () =>
      conversations.find((c) => c.id === selectedId) ??
      null,
    [conversations, selectedId],
  );

  const delta = selected ? playgroundScore - selected.score : 0;

  return (
    <div className="rounded-md border border-border bg-surface p-3 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <GitCompareArrows className="h-4 w-4 text-text-muted" aria-hidden />
          <Label
            htmlFor="playground-compare-toggle"
            className="text-xs font-semibold uppercase tracking-wide text-text-muted cursor-pointer"
          >
            Compare to a queue item
          </Label>
        </div>
        <Switch
          id="playground-compare-toggle"
          checked={enabled}
          onCheckedChange={setEnabled}
          aria-label="Toggle comparison to a queue item"
        />
      </div>

      {enabled && (
        <div className="space-y-3 animate-in fade-in-0 slide-in-from-top-1">
          <Select
            value={selectedId ?? undefined}
            onValueChange={(v) => setSelectedId(v)}
          >
            <SelectTrigger
              className="w-full"
              aria-label="Pick a conversation from the queue"
            >
              <SelectValue placeholder="Pick a conversation…" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Queue ({conversations.length})</SelectLabel>
                {conversations.slice(0, 60).map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    <span className="text-text-muted font-mono">
                      {c.score}
                    </span>
                    <span className="truncate">{c.message.slice(0, 60)}</span>
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>

          {selected ? (
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
              <CompareCell
                label="This message"
                score={playgroundScore}
                intent={playgroundIntent}
              />
              <DeltaPill delta={delta} />
              <CompareCell
                label="Queue item"
                score={selected.score}
                intent={selected.intent}
                subtitle={
                  <PlatformBadge
                    platform={selected.platform}
                    showLabel={false}
                  />
                }
              />
            </div>
          ) : (
            <p className="text-xs text-text-muted italic">
              Pick a conversation above to see the side-by-side comparison.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function CompareCell({
  label,
  score,
  intent,
  subtitle,
}: {
  label: string;
  score: number;
  intent: Conversation["intent"];
  subtitle?: React.ReactNode;
}) {
  return (
    <div className="rounded-md bg-surface-sunk/60 p-2.5 space-y-1.5 text-center">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
        {label}
      </p>
      <p
        data-num
        className="font-mono text-2xl font-semibold tabular-nums leading-none"
      >
        {score}
        <span className="text-xs text-text-muted ml-0.5">/100</span>
      </p>
      <IntentPill intent={intent} className="text-[10px]" />
      {subtitle && <div className="pt-0.5">{subtitle}</div>}
    </div>
  );
}

function DeltaPill({ delta }: { delta: number }) {
  if (delta === 0) {
    return (
      <div className="text-center text-[10px] font-semibold uppercase tracking-wide text-text-muted whitespace-nowrap">
        Even
      </div>
    );
  }
  const up = delta > 0;
  return (
    <div
      className={cn(
        "text-center whitespace-nowrap rounded-pill px-2 py-1 text-xs font-semibold tabular-nums",
        up ? "bg-success/10 text-success" : "bg-risk/10 text-risk",
      )}
      aria-label={`This message scores ${Math.abs(delta)} points ${up ? "higher" : "lower"} than the queue item`}
    >
      <span aria-hidden>{up ? "▲" : "▼"}</span>
      <span className="ml-0.5">{up ? "+" : "−"}{Math.abs(delta)}</span>
    </div>
  );
}
