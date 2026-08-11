"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useSignalStore } from "@/stores/signal-store";
import { PLATFORMS, COUNTRIES, DEFAULT_TUNING } from "@/lib/constants";
import type { Platform, TuningConfig } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Radar,
  Check,
  ChevronRight,
  ChevronLeft,
  X,
  Sparkles,
} from "lucide-react";

/* ============================================================
   OnboardingWizard — 4-step first-run wizard.
   Skippable, re-runnable from a help menu.
   Steps: pick platforms → pick countries → seed keywords → set voice
   ============================================================ */

type Step = 0 | 1 | 2 | 3;

const STEP_TITLES = [
  "Pick platforms to listen on",
  "Pick countries to focus on",
  "Seed your keywords",
  "Set your reply voice",
];

export function OnboardingWizard() {
  const [step, setStep] = React.useState<Step>(0);
  const [platforms, setPlatforms] = React.useState<Platform[]>([
    "discord",
    "telegram",
    "facebook",
    "reddit",
  ]);
  const [countries, setCountries] = React.useState<string[]>([
    "US",
    "GB",
    "CA",
    "AU",
  ]);
  const [keywords, setKeywords] = React.useState<string>(
    "free prediction game\nno deposit\nfree to play\nsocial prediction\nplay without depositing",
  );
  const [voice, setVoice] = React.useState({
    friendliness: 70,
    helpfulness: 80,
    formality: 35,
    ctaStrength: 55,
    emoji: 20,
  });
  const [maxLength, setMaxLength] = React.useState(280);

  const setOnboardingComplete = useSignalStore(
    (s) => s.setOnboardingComplete,
  );
  const setConfig = useSignalStore((s) => s.setConfig);

  function skip() {
    setOnboardingComplete(true);
  }

  function finish() {
    // Apply selections to the config
    const config: TuningConfig = JSON.parse(JSON.stringify(DEFAULT_TUNING));
    // countries: enable selected, disable others
    config.countries = config.countries.map((c) => ({
      ...c,
      enabled: countries.includes(c.code),
    }));
    // keywords: parse the textarea into keyword rules (phrase match)
    const lines = keywords
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const existing = new Set(config.keywords.map((k) => k.term.toLowerCase()));
    const added = lines
      .filter((l) => !existing.has(l.toLowerCase()))
      .map((term, i) => ({
        id: `kw_onboard_${Date.now()}_${i}`,
        term,
        matchType: "phrase" as const,
        priority: 3,
        weight: 12,
        hits7d: 0,
      }));
    config.keywords = [...config.keywords, ...added];
    // voice
    config.voice = {
      ...config.voice,
      ...voice,
      maxLength,
    };
    setConfig(config);
    setOnboardingComplete(true);
  }

  const next = () => setStep((s) => Math.min(3, s + 1) as Step);
  const prev = () => setStep((s) => Math.max(0, s - 1) as Step);

  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas p-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
        className="w-full max-w-2xl bg-surface border rounded-lg shadow-md-signal overflow-hidden"
        role="dialog"
        aria-labelledby="onboarding-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
              <Radar className="h-4 w-4" aria-hidden />
            </div>
            <span className="font-semibold">Welcome to Signal</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={skip}
            className="text-text-muted hover:text-text"
          >
            Skip <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Progress */}
        <div className="px-6 pt-4">
          <div className="flex items-center gap-2">
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className={cn(
                  "h-1 flex-1 rounded-pill transition-colors",
                  i <= step ? "bg-primary" : "bg-border",
                )}
                aria-hidden
              />
            ))}
          </div>
          <p className="text-xs text-text-muted mt-2">
            Step {step + 1} of 4 — {STEP_TITLES[step]}
          </p>
        </div>

        {/* Body */}
        <div className="px-6 py-5 min-h-[300px]">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              {step === 0 && (
                <StepPlatforms
                  selected={platforms}
                  onChange={setPlatforms}
                />
              )}
              {step === 1 && (
                <StepCountries
                  selected={countries}
                  onChange={setCountries}
                />
              )}
              {step === 2 && (
                <StepKeywords value={keywords} onChange={setKeywords} />
              )}
              {step === 3 && (
                <StepVoice
                  voice={voice}
                  onVoiceChange={setVoice}
                  maxLength={maxLength}
                  onMaxLengthChange={setMaxLength}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t bg-surface-sunk/40">
          <Button
            variant="ghost"
            size="sm"
            onClick={step === 0 ? skip : prev}
            className="text-text-muted hover:text-text"
          >
            {step === 0 ? (
              "Skip setup"
            ) : (
              <>
                <ChevronLeft className="h-3.5 w-3.5 mr-1" /> Back
              </>
            )}
          </Button>
          {step < 3 ? (
            <Button size="sm" onClick={next}>
              Continue <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          ) : (
            <Button size="sm" onClick={finish}>
              <Check className="h-3.5 w-3.5 mr-1" /> Finish setup
            </Button>
          )}
        </div>
      </motion.div>
    </div>
  );
}

/* ---------------- Step components ---------------- */

function StepPlatforms({
  selected,
  onChange,
}: {
  selected: Platform[];
  onChange: (p: Platform[]) => void;
}) {
  const toggle = (p: Platform) => {
    onChange(
      selected.includes(p)
        ? selected.filter((x) => x !== p)
        : [...selected, p],
    );
  };
  return (
    <div>
      <h2 className="text-lg font-semibold">Pick platforms to listen on</h2>
      <p className="text-sm text-text-muted mt-1 mb-4">
        Signal reads public posts on these platforms. You can change this later in
        Tuning.
      </p>
      <div className="grid grid-cols-2 gap-3">
        {(Object.keys(PLATFORMS) as Platform[]).map((p) => {
          const meta = PLATFORMS[p];
          const active = selected.includes(p);
          return (
            <button
              key={p}
              type="button"
              onClick={() => toggle(p)}
              aria-pressed={active}
              className={cn(
                "flex items-center gap-3 p-4 rounded-md border text-left transition-colors",
                active
                  ? "border-primary bg-primary-soft"
                  : "border-border hover:bg-surface-sunk",
              )}
            >
              <span className="text-2xl" aria-hidden>
                {meta.glyph}
              </span>
              <div className="flex-1">
                <p className="font-medium">{meta.label}</p>
                <p className="text-xs text-text-muted">Public posts &amp; threads</p>
              </div>
              {active && <Check className="h-4 w-4 text-primary" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function StepCountries({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (c: string[]) => void;
}) {
  const toggle = (code: string) => {
    onChange(
      selected.includes(code)
        ? selected.filter((x) => x !== code)
        : [...selected, code],
    );
  };
  return (
    <div>
      <h2 className="text-lg font-semibold">Pick countries to focus on</h2>
      <p className="text-sm text-text-muted mt-1 mb-4">
        Posts from these countries score higher. Everywhere else still gets picked
        up, just ranked lower.
      </p>
      <div className="grid grid-cols-3 gap-2">
        {COUNTRIES.map((c) => {
          const active = selected.includes(c.code);
          return (
            <button
              key={c.code}
              type="button"
              onClick={() => toggle(c.code)}
              aria-pressed={active}
              className={cn(
                "flex items-center gap-2 p-2 rounded-md border text-left text-sm transition-colors",
                active
                  ? "border-primary bg-primary-soft"
                  : "border-border hover:bg-surface-sunk",
              )}
            >
              <span className="text-lg" aria-hidden>
                {c.flag}
              </span>
              <span className="flex-1 truncate">{c.name}</span>
              {active && <Check className="h-3.5 w-3.5 text-primary" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function StepKeywords({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <h2 className="text-lg font-semibold">Seed your keywords</h2>
      <p className="text-sm text-text-muted mt-1 mb-4">
        One phrase per line. Each becomes a phrase-match rule at default weight,
        which you can adjust later in Tuning.
      </p>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={8}
        className="font-mono text-sm"
        placeholder={"free prediction game\nno deposit\nfree to play"}
      />
      <p className="text-xs text-text-muted mt-2">
        {value.split("\n").filter((l) => l.trim()).length} keyword
        {value.split("\n").filter((l) => l.trim()).length === 1 ? "" : "s"}{" "}
        entered
      </p>
    </div>
  );
}

function StepVoice({
  voice,
  onVoiceChange,
  maxLength,
  onMaxLengthChange,
}: {
  voice: {
    friendliness: number;
    helpfulness: number;
    formality: number;
    ctaStrength: number;
    emoji: number;
  };
  onVoiceChange: (v: typeof voice) => void;
  maxLength: number;
  onMaxLengthChange: (n: number) => void;
}) {
  const sliders: { key: keyof typeof voice; label: string }[] = [
    { key: "friendliness", label: "Friendliness" },
    { key: "helpfulness", label: "Helpfulness" },
    { key: "formality", label: "Formality" },
    { key: "ctaStrength", label: "CTA strength" },
    { key: "emoji", label: "Emoji" },
  ];
  return (
    <div>
      <h2 className="text-lg font-semibold">Set your reply voice</h2>
      <p className="text-sm text-text-muted mt-1 mb-4">
        Move the dials until a draft sounds like you. Disclosure and the
        free-to-play note stay locked either way.
      </p>
      <div className="space-y-4">
        {sliders.map(({ key, label }) => (
          <div key={key}>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-medium" htmlFor={`voice-${key}`}>
                {label}
              </label>
              <span className="font-mono text-sm tabular-nums text-text-muted">
                {voice[key]}
              </span>
            </div>
            <Slider
              id={`voice-${key}`}
              value={[voice[key]]}
              onValueChange={(v) =>
                onVoiceChange({ ...voice, [key]: v[0] })
              }
              min={0}
              max={100}
              step={1}
              aria-label={label}
            />
          </div>
        ))}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-sm font-medium" htmlFor="max-length">
              Max reply length
            </label>
            <span className="font-mono text-sm tabular-nums text-text-muted">
              {maxLength} chars
            </span>
          </div>
          <Input
            id="max-length"
            type="number"
            min={80}
            max={600}
            value={maxLength}
            onChange={(e) =>
              onMaxLengthChange(
                Math.max(80, Math.min(600, Number(e.target.value) || 280)),
              )
            }
          />
        </div>
      </div>
    </div>
  );
}
