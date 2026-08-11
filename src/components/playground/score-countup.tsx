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

/**
 * ScoreCountup — large mono numeral that animates from 0 to `score`
 * over 600ms using Framer Motion's animate(). Honours
 * prefers-reduced-motion (renders the final number immediately).
 */
export function ScoreCountup({
  score,
  className,
}: {
  score: number;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const mv = useMotionValue(0);
  const text: MotionValue<string> = useTransform(
    mv,
    (v) => String(Math.round(v)),
  );

  React.useEffect(() => {
    if (reduced) {
      mv.set(score);
      return;
    }
    mv.set(0);
    const controls = animate(mv, score, {
      duration: 0.6,
      ease: "easeOut",
    });
    return () => controls.stop();
  }, [score, mv, reduced]);

  return (
    <div className={className} aria-live="off">
      <motion.span
        data-num
        aria-label={`Score ${score} out of 100`}
        className="font-mono font-semibold tabular-nums leading-none"
        style={{ fontSize: 56 }}
      >
        {text}
      </motion.span>
      <span className="ml-1 text-xl text-text-muted font-mono tabular-nums">
        /100
      </span>
    </div>
  );
}
