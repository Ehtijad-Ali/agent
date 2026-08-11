"use client";

import * as React from "react";
import { COUNTRIES } from "@/lib/constants";
import type { Conversation } from "@/lib/types";

/* Country heat list — top 8 countries by conversation count.
   Each row: flag + name + count + horizontal bar showing approval rate %. */

interface CountryRow {
  code: string;
  name: string;
  flag: string;
  count: number;
  approved: number;
  approvalRate: number;
}

function buildRows(convos: Conversation[]): CountryRow[] {
  const map = new Map<string, { count: number; approved: number }>();
  for (const c of convos) {
    const cur = map.get(c.country) ?? { count: 0, approved: 0 };
    cur.count += 1;
    if (c.status === "approved") cur.approved += 1;
    map.set(c.country, cur);
  }
  const rows: CountryRow[] = [];
  for (const [code, v] of map.entries()) {
    const meta = COUNTRIES.find((x) => x.code === code);
    rows.push({
      code,
      name: meta?.name ?? code,
      flag: meta?.flag ?? "🏳️",
      count: v.count,
      approved: v.approved,
      approvalRate: v.count === 0 ? 0 : (v.approved / v.count) * 100,
    });
  }
  rows.sort((a, b) => b.count - a.count);
  return rows.slice(0, 8);
}

export function CountryHeat({ convos }: { convos: Conversation[] }) {
  const rows = React.useMemo(() => buildRows(convos), [convos]);
  const maxCount = Math.max(1, ...rows.map((r) => r.count));
  if (rows.length === 0) {
    return (
      <p className="text-sm text-text-muted py-8 text-center">
        No country data in this range.
      </p>
    );
  }
  return (
    <div
      role="img"
      aria-label={`Top countries by conversation count. ${rows
        .map(
          (r) =>
            `${r.name}: ${r.count} conversations, ${Math.round(r.approvalRate)}% approval`,
        )
        .join(". ")}`}
    >
      <ul className="space-y-3">
        {rows.map((r) => (
          <li key={r.code} className="space-y-1.5">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="inline-flex items-center gap-2 min-w-0">
                <span aria-hidden className="text-base leading-none">
                  {r.flag}
                </span>
                <span className="font-medium text-text truncate">{r.name}</span>
                <span className="text-text-muted font-mono tabular-nums">
                  {r.count}
                </span>
              </span>
              <span className="text-text-muted font-mono tabular-nums">
                {Math.round(r.approvalRate)}% approval
              </span>
            </div>
            <div className="relative h-2.5 rounded-pill bg-surface-sunk overflow-hidden">
              {/* Volume track (grey) */}
              <div
                className="absolute inset-y-0 left-0 rounded-pill"
                aria-hidden
                style={{
                  width: `${(r.count / maxCount) * 100}%`,
                  background: "var(--text-muted)",
                  opacity: 0.22,
                }}
              />
              {/* Approval rate (teal) on top */}
              <div
                className="absolute inset-y-0 left-0 rounded-pill"
                aria-hidden
                style={{
                  width: `${(r.approvalRate / 100) * (r.count / maxCount) * 100}%`,
                  background: "var(--primary)",
                  opacity: 0.85,
                }}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] text-text-muted">
              <span>{r.approved} approved</span>
              <span>{r.count - r.approved} other</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
