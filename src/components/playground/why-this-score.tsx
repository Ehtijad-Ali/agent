"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Contribution = {
  ruleId: string;
  label: string;
  points: number;
};

/**
 * WhyThisScore — collapsible expander that, when opened, lists every
 * contribution with its rule label and signed points (+14, -15, etc.).
 */
export function WhyThisScore({
  contributions,
}: {
  contributions: Contribution[];
}) {
  const [open, setOpen] = React.useState(false);
  const total = contributions.reduce((s, c) => s + c.points, 0);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-md border border-border bg-surface">
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-between px-3 py-2 h-auto text-xs font-semibold uppercase tracking-wide text-text-muted hover:bg-surface-sunk hover:text-text"
          aria-expanded={open}
          aria-controls="why-this-score-content"
        >
          <span>Why this score? · {contributions.length} rules</span>
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 transition-transform",
              open && "rotate-180",
            )}
            aria-hidden
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent
        id="why-this-score-content"
        className="data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-1 data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
      >
        <div className="border-t border-border">
          <table className="w-full text-xs">
            <thead className="sr-only">
              <tr>
                <th>Rule</th>
                <th>Points</th>
              </tr>
            </thead>
            <tbody>
              {contributions.length === 0 && (
                <tr>
                  <td
                    colSpan={2}
                    className="px-3 py-3 text-text-muted italic"
                  >
                    No scoring rules matched.
                  </td>
                </tr>
              )}
              {contributions.map((c) => (
                <tr
                  key={c.ruleId}
                  className="border-b border-border/60 last:border-b-0"
                >
                  <td className="px-3 py-1.5 text-text align-top">
                    {c.label}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-1.5 text-right font-mono tabular-nums font-semibold align-top whitespace-nowrap",
                      c.points > 0 ? "text-success" : c.points < 0 ? "text-risk" : "text-text-muted",
                    )}
                  >
                    {c.points > 0 ? "+" : ""}
                    {c.points}
                  </td>
                </tr>
              ))}
              {contributions.length > 0 && (
                <tr className="bg-surface-sunk/60">
                  <td className="px-3 py-1.5 font-semibold text-text">
                    Total (clamped 0–100)
                  </td>
                  <td
                    className={cn(
                      "px-3 py-1.5 text-right font-mono tabular-nums font-semibold",
                      total > 0 ? "text-success" : total < 0 ? "text-risk" : "text-text-muted",
                    )}
                  >
                    {total > 0 ? "+" : ""}
                    {total}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
