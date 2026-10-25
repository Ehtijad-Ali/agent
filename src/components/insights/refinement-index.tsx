"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  type RefinementIndex,
  ApiError,
  getAgentRefinement,
  getRefinementIndex,
  listAgents,
} from "@/lib/api";

/* Agent Refinement Index (brief §8) — one 0-100 score for how well the
   pipeline turns discovered messages into approved, clicked replies, overall
   and per engagement agent. Computed on the server from the last 30 days. */

function tone(score: number, confident: boolean): string {
  if (!confident) return "text-text-muted";
  if (score >= 70) return "text-success";
  if (score >= 40) return "text-warning";
  return "text-risk";
}

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function Components({ index }: { index: RefinementIndex }) {
  const parts = [
    { label: "Approval rate", value: index.approvalRate, hint: "Relevant leads a reviewer approved" },
    { label: "Precision", value: index.precision, hint: "Discovered messages that were relevant" },
    { label: "Click-through", value: index.clickThroughRate, hint: "Sent replies whose link was clicked" },
  ];
  return (
    <div className="grid grid-cols-3 gap-2">
      {parts.map((p) => (
        <div key={p.label} className="rounded-md border border-border bg-surface p-2" title={p.hint}>
          <p className="text-[11px] text-text-muted">{p.label}</p>
          <p className="font-mono tabular-nums text-sm font-semibold text-text">{pct(p.value)}</p>
          <div className="mt-1 h-1 rounded bg-surface-sunk">
            <div className="h-1 rounded bg-primary" style={{ width: pct(Math.min(1, p.value)) }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function RefinementIndexCard() {
  const [overall, setOverall] = React.useState<RefinementIndex | null>(null);
  const [perAgent, setPerAgent] = React.useState<RefinementIndex[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [index, agents] = await Promise.all([
          getRefinementIndex(30),
          listAgents({ type: "engagement" }),
        ]);
        const scored = await Promise.all(agents.map((a) => getAgentRefinement(a.id, 30)));
        if (!alive) return;
        setOverall(index);
        setPerAgent(scored);
      } catch (cause) {
        if (alive) setError(cause instanceof ApiError ? cause.message : "Could not load the index.");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="text-sm text-risk">{error}</p>;
  if (!overall) {
    return (
      <p className="flex items-center gap-2 text-sm text-text-muted">
        <Loader2 className="h-4 w-4 animate-spin" /> Calculating…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-[120px]">
          <p
            className={cn(
              "text-4xl font-semibold font-mono tabular-nums",
              tone(overall.score, overall.confident),
            )}
          >
            {overall.score.toFixed(1)}
          </p>
          <p className="text-xs text-text-muted">
            out of 100 · {overall.sampleSize} conversation{overall.sampleSize === 1 ? "" : "s"}
            {overall.confident ? "" : " · not enough data yet"}
          </p>
        </div>
        <div className="min-w-[240px] flex-1">
          <Components index={overall} />
        </div>
      </div>

      {overall.notes.length > 0 ? (
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-text-muted">
          {overall.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}

      {perAgent.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Per agent</p>
          <ul className="divide-y divide-border rounded-md border border-border">
            {perAgent.map((a) => (
              <li
                key={a.agentId ?? "all"}
                className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
              >
                <span className="min-w-0 truncate text-text">{a.agentName}</span>
                <span className="flex items-center gap-3 text-xs text-text-muted">
                  <span>{a.sampleSize} convos</span>
                  <span
                    className={cn(
                      "font-mono tabular-nums text-sm font-semibold",
                      tone(a.score, a.confident),
                    )}
                  >
                    {a.score.toFixed(1)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
