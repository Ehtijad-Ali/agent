"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import { DEFAULT_TUNING } from "@/lib/constants";
import type { ScoringConfig, Thresholds, TuningConfig } from "@/lib/types";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { ThresholdEditor } from "./threshold-editor";
import { RotateCcw } from "lucide-react";

function clone(c: TuningConfig): TuningConfig {
  return JSON.parse(JSON.stringify(c));
}

const BOOST_LABELS: { key: keyof ScoringConfig["boosts"]; label: string }[] = [
  { key: "asksRecommendation", label: "Asks for recommendation" },
  { key: "mentionsNoDeposit", label: "Mentions no deposit" },
  { key: "mentionsFree", label: "Mentions free" },
  { key: "mentionsGame", label: "Mentions game" },
  { key: "mentionsSocial", label: "Mentions social" },
  { key: "highPriorityCountry", label: "High-priority country" },
  { key: "recentPost", label: "Recent post (<24h)" },
];

const PENALTY_LABELS: {
  key: keyof ScoringConfig["penalties"];
  label: string;
}[] = [
  { key: "negativeKeyword", label: "Negative keyword" },
  { key: "offTopic", label: "Off-topic" },
  { key: "promotional", label: "Promotional" },
  { key: "lowPriorityCountry", label: "Low-priority country" },
];

function SliderRow({
  label,
  value,
  min,
  max,
  onValueChange,
  onNumberChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onValueChange: (v: number) => void;
  onNumberChange: (v: number) => void;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-3">
      <div className="flex items-center gap-3">
        <span className="text-sm w-44 shrink-0">{label}</span>
        <Slider
          value={[value]}
          min={min}
          max={max}
          step={1}
          onValueChange={(v) => onValueChange(v[0])}
          aria-label={label}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={value}
          className="flex-1"
        />
      </div>
      <Input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) =>
          onNumberChange(
            Math.max(min, Math.min(max, Number(e.target.value) || 0)),
          )
        }
        className="w-16 h-8"
        aria-label={`${label} value`}
      />
    </div>
  );
}

/**
 * SectionScoring — boosts (0-30) and penalties (-30 to 0) sliders, the
 * 4-stop threshold editor with live band counts, and a Reset-to-defaults
 * button guarded by an AlertDialog.
 */
export function SectionScoring() {
  const config = useSignalStore((s) => s.config);
  const draftConfig = useSignalStore((s) => s.draftConfig);
  const setDraftConfig = useSignalStore((s) => s.setDraftConfig);
  const previewSamples = useSignalStore((s) => s.previewSamples);
  const active = draftConfig ?? config;

  function setBoost(key: keyof ScoringConfig["boosts"], v: number) {
    setDraftConfig({
      ...clone(active),
      scoring: {
        ...active.scoring,
        boosts: { ...active.scoring.boosts, [key]: v },
      },
    });
  }
  function setPenalty(key: keyof ScoringConfig["penalties"], v: number) {
    setDraftConfig({
      ...clone(active),
      scoring: {
        ...active.scoring,
        penalties: { ...active.scoring.penalties, [key]: v },
      },
    });
  }
  function setThresholds(t: Thresholds) {
    setDraftConfig({ ...clone(active), thresholds: t });
  }
  function resetDefaults() {
    setDraftConfig(JSON.parse(JSON.stringify(DEFAULT_TUNING)));
  }

  const counts = React.useMemo(() => {
    const c = { notRelevant: 0, low: 0, medium: 0, high: 0 };
    const t = active.thresholds;
    previewSamples.forEach((s) => {
      const hasRisk = s.riskFlags.length > 0;
      if (hasRisk || s.score < t.notRelevant) c.notRelevant++;
      else if (s.score < t.low) c.low++;
      else if (s.score < t.medium) c.medium++;
      else c.high++;
    });
    return c;
  }, [previewSamples, active.thresholds]);

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Boosts
        </h3>
        {BOOST_LABELS.map(({ key, label }) => (
          <SliderRow
            key={key}
            label={label}
            value={active.scoring.boosts[key]}
            min={0}
            max={30}
            onValueChange={(v) => setBoost(key, v)}
            onNumberChange={(v) => setBoost(key, v)}
          />
        ))}
      </div>

      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Penalties
        </h3>
        {PENALTY_LABELS.map(({ key, label }) => (
          <SliderRow
            key={key}
            label={label}
            value={active.scoring.penalties[key]}
            min={-30}
            max={0}
            onValueChange={(v) => setPenalty(key, v)}
            onNumberChange={(v) => setPenalty(key, v)}
          />
        ))}
      </div>

      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Intent thresholds
        </h3>
        <ThresholdEditor
          thresholds={active.thresholds}
          counts={counts}
          onChange={setThresholds}
        />
      </div>

      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="text-text-muted"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden /> Reset to defaults
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Reset all tuning to defaults?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This loads the factory defaults into your draft. Your saved
              config is not changed until you click Save in the unsaved bar.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={resetDefaults}>
              Reset
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
