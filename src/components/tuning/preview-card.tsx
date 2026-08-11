"use client";

import * as React from "react";
import {
  animate,
  motion,
  useMotionValue,
  useTransform,
  useReducedMotion,
  type MotionValue,
} from "framer-motion";
import type { Conversation } from "@/lib/types";
import { IntentPill } from "@/components/signal/primitives";
import { cn } from "@/lib/utils";

/**
 * PreviewCard — single preview-sample row in the right-hand Live preview.
 * Score is an animated count-up/down using a MotionValue → useTransform →
 * motion.span text child. Delta chip shows green ▲ / red ▼ vs baseline
 * (committed config). Renders nothing when delta is 0 or hidden.
 */
export function PreviewCard({
  sample,
  baselineScore,
  showDelta,
}: {
  sample: Conversation;
  baselineScore: number;
  showDelta: boolean;
}) {
  const reduced = useReducedMotion();
  const mv = useMotionValue(sample.score);
  const text: MotionValue<string> = useTransform(
    mv,
    (v) => String(Math.round(v)),
  );

  React.useEffect(() => {
    if (reduced) {
      mv.set(sample.score);
      return;
    }
    const controls = animate(mv, sample.score, {
      duration: 0.18,
      ease: "easeOut",
    });
    return () => controls.stop();
  }, [sample.score, mv, reduced]);

  const delta = sample.score - baselineScore;
  const hasDelta = showDelta && delta !== 0;

  return (
    <article className="rounded-md border bg-surface p-3 space-y-2 shadow-sm-signal">
      <p
        className="text-xs text-text-muted line-clamp-1"
        title={sample.message}
      >
        {sample.message}
      </p>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-baseline gap-1.5">
          <motion.span
            className="font-mono text-2xl font-semibold tabular-nums leading-none"
            data-num
            aria-label={`Score ${sample.score} out of 100`}
          >
            {text}
          </motion.span>
          <span className="text-xs text-text-muted">/100</span>
          {hasDelta && (
            <span
              className={cn(
                "ml-1 inline-flex items-center gap-0.5 text-xs font-medium tabular-nums",
                delta > 0 ? "text-success" : "text-risk",
              )}
              aria-label={`Score ${delta > 0 ? "increased" : "decreased"} by ${Math.abs(delta)} points`}
            >
              <span aria-hidden>{delta > 0 ? "▲" : "▼"}</span>
              {Math.abs(delta)}
            </span>
          )}
        </div>
        <IntentPill intent={sample.intent} />
      </div>
    </article>
  );
}
