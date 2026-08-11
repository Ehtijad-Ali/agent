"use client";

import * as React from "react";
import type { Thresholds } from "@/lib/types";

/**
 * ThresholdEditor — a single 0-100 track with four draggable stops
 * (notRelevant / low / medium / high). Handles are pointer-draggable AND
 * keyboard-operable (←/→ to move by 1, with shift for ±5). Stops must
 * maintain ordering (notRelevant ≤ low ≤ medium ≤ high) — we clamp on
 * every change.
 */
const STOPS = [
  {
    key: "notRelevant" as const,
    label: "Not relevant",
    color: "var(--text-muted)",
  },
  {
    key: "low" as const,
    label: "Low",
    color: "var(--info)",
  },
  {
    key: "medium" as const,
    label: "Medium",
    color: "var(--warning)",
  },
  {
    key: "high" as const,
    label: "High",
    color: "var(--primary)",
  },
];

export function ThresholdEditor({
  thresholds,
  counts,
  onChange,
}: {
  thresholds: Thresholds;
  counts?: { notRelevant: number; low: number; medium: number; high: number };
  onChange: (t: Thresholds) => void;
}) {
  const trackRef = React.useRef<HTMLDivElement>(null);

  function setStop(key: keyof Thresholds, raw: number) {
    const v = Math.max(0, Math.min(100, Math.round(raw)));
    const next: Thresholds = { ...thresholds, [key]: v };
    if (key === "notRelevant") next.notRelevant = Math.min(v, thresholds.low);
    if (key === "low") {
      next.low = Math.max(v, thresholds.notRelevant);
      next.low = Math.min(next.low, thresholds.medium);
    }
    if (key === "medium") {
      next.medium = Math.max(v, thresholds.low);
      next.medium = Math.min(next.medium, thresholds.high);
    }
    if (key === "high") next.high = Math.max(v, thresholds.medium);
    onChange(next);
  }

  function onPointerDown(
    e: React.PointerEvent<HTMLButtonElement>,
    key: keyof Thresholds,
  ) {
    e.preventDefault();
    const handle = e.currentTarget;
    try {
      handle.setPointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    const track = trackRef.current;
    if (!track) return;

    function move(ev: PointerEvent) {
      if (!track) return;
      const rect = track.getBoundingClientRect();
      const pct = ((ev.clientX - rect.left) / rect.width) * 100;
      setStop(key, pct);
    }
    function up(ev: PointerEvent) {
      try {
        handle.releasePointerCapture(ev.pointerId);
      } catch {
        /* ignore */
      }
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
    }
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  }

  function onKey(
    e: React.KeyboardEvent<HTMLButtonElement>,
    key: keyof Thresholds,
  ) {
    const step = e.shiftKey ? 5 : 1;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      setStop(key, thresholds[key] - step);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      setStop(key, thresholds[key] + step);
    } else if (e.key === "Home") {
      e.preventDefault();
      setStop(key, 0);
    } else if (e.key === "End") {
      e.preventDefault();
      setStop(key, 100);
    }
  }

  return (
    <div className="space-y-3">
      <div
        ref={trackRef}
        className="relative h-8 rounded-pill bg-surface-sunk border"
        aria-hidden
      >
        {STOPS.map((s) => (
          <button
            key={s.key}
            type="button"
            role="slider"
            aria-label={s.label}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={thresholds[s.key]}
            aria-valuetext={`${thresholds[s.key]} out of 100`}
            tabIndex={0}
            onPointerDown={(e) => onPointerDown(e, s.key)}
            onKeyDown={(e) => onKey(e, s.key)}
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-5 h-5 rounded-full border-2 bg-surface shadow-sm-signal cursor-grab active:cursor-grabbing focus-visible:outline-2 focus-visible:outline-offset-2 hover:scale-110 transition-transform"
            style={{
              left: `${thresholds[s.key]}%`,
              borderColor: s.color,
            }}
          />
        ))}
      </div>

      <div className="grid grid-cols-4 gap-2 text-xs">
        {STOPS.map((s) => (
          <div key={s.key} className="text-center">
            <div className="text-text-muted">{s.label}</div>
            <div
              className="font-mono font-semibold tabular-nums"
              style={{ color: s.color }}
            >
              {thresholds[s.key]}
            </div>
            {counts && (
              <div className="text-text-muted text-[11px] tabular-nums">
                {counts[s.key]} conv.
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
