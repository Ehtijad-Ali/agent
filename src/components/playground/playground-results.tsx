"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Copy, FlaskConical, Loader2, MessageSquareQuote } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  IntentPill,
  RiskPill,
  ScoreBreakdownBar,
  EmptyState,
} from "@/components/signal/primitives";
import { ScoreCountup } from "./score-countup";
import { WhyThisScore } from "./why-this-score";
import { CompareToQueue } from "./compare-to-queue";
import { confidenceExplanation } from "@/lib/scoring";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import type { AnalyseResult } from "@/lib/mockApi";
import type { Conversation, Intent, RiskFlag } from "@/lib/types";

const LANGUAGE_NAMES: Record<string, string> = {
  en: "English",
  pt: "Portuguese",
  fr: "French",
  de: "German",
  es: "Spanish",
};

const CONFIDENCE_LABEL = {
  low: "Low confidence",
  medium: "Medium confidence",
  high: "High confidence",
} as const;

const CONFIDENCE_TONE = {
  low: "text-text-muted",
  medium: "text-warning",
  high: "text-success",
} as const;

const CONFIDENCE_FILL = {
  low: "var(--text-muted)",
  medium: "var(--warning)",
  high: "var(--success)",
} as const;

const CONFIDENCE_PCT = { low: "25%", medium: "60%", high: "100%" } as const;

/**
 * PlaygroundResults — right pane. Three visual states: empty / loading /
 * result. Result renders the 10 spec'd sections in order, faded in
 * with Framer Motion (150ms ease-out).
 */
export function PlaygroundResults({
  loading,
  result,
}: {
  loading: boolean;
  result: AnalyseResult | null;
}) {
  return (
    <div className="relative h-full">
      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
          >
            <LoadingState />
          </motion.div>
        ) : result ? (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
          >
            <ResultBody result={result} />
          </motion.div>
        ) : (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
          >
            <EmptyState
              icon={FlaskConical}
              title="Nothing analysed yet"
              description="Paste a message on the left and hit Analyse. You will get a score, the rules that fired, and a draft reply."
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function LoadingState() {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 py-20 text-center"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-8 w-8 animate-spin text-primary" aria-hidden />
      <p className="text-sm text-text-muted">Running the scoring engine…</p>
    </div>
  );
}

function ResultBody({ result }: { result: AnalyseResult }) {
  const { toast } = useToast();
  const [copied, setCopied] = React.useState(false);

  const intent = result.intent as Intent;
  const langName = LANGUAGE_NAMES[result.language] ?? result.language.toUpperCase();

  const handleCopy = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(result.reply);
      setCopied(true);
      toast({
        title: "Reply copied to clipboard",
        duration: 2200,
      });
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast({
        title: "Could not copy",
        description: "Clipboard permission was denied.",
        duration: 2600,
      });
    }
  }, [result.reply, toast]);

  return (
    <div className="space-y-6">
      {/* 1 + 2. Score countup + Intent pill */}
      <section className="space-y-3">
        <ScoreCountup score={result.score} />
        <div className="flex items-center gap-2 flex-wrap">
          <IntentPill intent={intent} />
          {result.riskFlags.length > 0 && (
            <span className="text-xs text-text-muted">
              · flagged by risk filters
            </span>
          )}
        </div>
      </section>

      {/* 3. Confidence meter + explanation */}
      <section className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Confidence
        </p>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 rounded-full bg-surface-sunk overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: CONFIDENCE_PCT[result.confidence],
                background: CONFIDENCE_FILL[result.confidence],
              }}
            />
          </div>
          <span
            className={cn(
              "text-xs font-medium whitespace-nowrap",
              CONFIDENCE_TONE[result.confidence],
            )}
          >
            {CONFIDENCE_LABEL[result.confidence]}
          </span>
        </div>
        <p className="text-xs text-text-muted leading-relaxed">
          {confidenceExplanation(
            result.confidence,
            result.contributions,
          )}
        </p>
      </section>

      {/* 4. Matched keyword chips */}
      <section className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Matched keywords · {result.matchedKeywords.length}
        </p>
        <div className="flex items-center gap-1.5 flex-wrap">
          {result.matchedKeywords.length === 0 ? (
            <span className="text-xs text-text-muted italic">
              None matched
            </span>
          ) : (
            result.matchedKeywords.map((kw) => (
              <Badge
                key={kw}
                variant="outline"
                className="bg-primary-soft text-primary border-transparent font-mono"
              >
                {kw}
              </Badge>
            ))
          )}
        </div>
      </section>

      {/* 5. Score breakdown bar */}
      <section className="space-y-2">
        <div className="flex items-baseline justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Score breakdown
          </p>
          <span className="font-mono text-xs text-text-muted">
            {result.contributions.length} contributions
          </span>
        </div>
        <ScoreBreakdownBar contributions={result.contributions} />
      </section>

      {/* 6. Detected language */}
      <section>
        <p className="text-xs text-text-muted">
          Detected language:{" "}
          <span className="text-text font-medium">{langName}</span>{" "}
          <span className="font-mono text-text-muted">({result.language})</span>
        </p>
      </section>

      {/* 7. Risk flags */}
      {result.riskFlags.length > 0 && (
        <section className="space-y-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Risk flags
          </p>
          <div className="flex items-center gap-1.5 flex-wrap">
            {result.riskFlags.map((f) => (
              <RiskPill key={f} flag={f as RiskFlag} />
            ))}
          </div>
        </section>
      )}

      {/* 8. Drafted reply */}
      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
            <MessageSquareQuote className="h-3.5 w-3.5" aria-hidden />
            Drafted reply · {result.replyVariants[0]?.tone ?? "helpful"}
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={handleCopy}
            aria-label="Copy the drafted reply to clipboard"
            className="h-7 gap-1.5 text-xs"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-success" aria-hidden />
                Copied
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" aria-hidden />
                Copy
              </>
            )}
          </Button>
        </div>
        <blockquote className="border-l-2 border-primary/40 pl-3 pr-2 py-2 text-sm text-text bg-surface-sunk/40 rounded-r-md leading-relaxed">
          {result.reply || (
            <span className="text-text-muted italic">No reply drafted.</span>
          )}
        </blockquote>
      </section>

      {/* 9. Why this score expander */}
      <WhyThisScore contributions={result.contributions} />

      {/* 10. Compare to a queue item */}
      <CompareToQueue
        playgroundScore={result.score}
        playgroundIntent={intent as Conversation["intent"]}
      />
    </div>
  );
}
