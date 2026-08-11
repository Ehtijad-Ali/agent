"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import { draftReply } from "@/lib/scoring";
import { NON_NEGOTIABLE_RULES } from "@/lib/constants";
import type { TuningConfig, VoiceConfig } from "@/lib/types";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Lock } from "lucide-react";

function clone(c: TuningConfig): TuningConfig {
  return JSON.parse(JSON.stringify(c));
}

const SLIDERS: { key: keyof VoiceConfig; label: string }[] = [
  { key: "friendliness", label: "Friendliness" },
  { key: "helpfulness", label: "Helpfulness" },
  { key: "formality", label: "Formality" },
  { key: "ctaStrength", label: "CTA strength" },
  { key: "emoji", label: "Emoji" },
];

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "pt", label: "Portuguese" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "es", label: "Spanish" },
];

/**
 * SectionVoice — five tone sliders (0-100), a max-length input (80-600),
 * a live sample reply that re-writes itself as the dials move (using the
 * first preview sample + draftReply), and the non-negotiable safety rules
 * rendered as locked Switch toggles.
 */
export function SectionVoice() {
  const config = useSignalStore((s) => s.config);
  const draftConfig = useSignalStore((s) => s.draftConfig);
  const setDraftConfig = useSignalStore((s) => s.setDraftConfig);
  const previewSamples = useSignalStore((s) => s.previewSamples);
  const active = draftConfig ?? config;
  const sample = previewSamples[0];

  function setVoiceNumber(key: keyof VoiceConfig, v: number) {
    setDraftConfig({
      ...clone(active),
      voice: { ...active.voice, [key]: v } as VoiceConfig,
    });
  }
  function setLanguage(lang: string) {
    setDraftConfig({
      ...clone(active),
      voice: { ...active.voice, replyLanguage: lang },
    });
  }

  const reply = sample
    ? draftReply(
        {
          message: sample.message,
          platform: sample.platform,
          community: sample.community,
          country: sample.country,
          matchedKeywords: sample.matchedKeywords,
        },
        "helpful",
        active.voice,
      )
    : "";

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        {SLIDERS.map(({ key, label }) => {
          const value = active.voice[key] as number;
          return (
            <div
              key={key}
              className="grid grid-cols-[1fr_auto] items-center gap-3"
            >
              <div className="flex items-center gap-3">
                <span className="text-sm w-32 shrink-0">{label}</span>
                <Slider
                  value={[value]}
                  min={0}
                  max={100}
                  step={1}
                  onValueChange={(v) => setVoiceNumber(key, v[0])}
                  aria-label={label}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={value}
                  className="flex-1"
                />
              </div>
              <Input
                type="number"
                min={0}
                max={100}
                value={value}
                onChange={(e) =>
                  setVoiceNumber(
                    key,
                    Math.max(0, Math.min(100, Number(e.target.value) || 0)),
                  )
                }
                className="w-16 h-8"
                aria-label={`${label} value`}
              />
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-[1fr_auto] items-center gap-3">
        <div className="flex items-center gap-3">
          <span className="text-sm w-32 shrink-0">Max length</span>
          <span className="text-xs text-text-muted flex-1">
            Characters per reply (80–600)
          </span>
        </div>
        <Input
          type="number"
          min={80}
          max={600}
          value={active.voice.maxLength}
          onChange={(e) =>
            setVoiceNumber(
              "maxLength",
              Math.max(80, Math.min(600, Number(e.target.value) || 80)),
            )
          }
          className="w-20 h-8"
          aria-label="Max reply length"
        />
      </div>

      <div className="grid grid-cols-[1fr_auto] items-center gap-3">
        <div>
          <div className="text-sm font-medium">Reply language</div>
          <p className="text-xs text-text-muted mt-0.5">
            Replies must match source language. We&apos;ll detect and adjust.
          </p>
        </div>
        <Select
          value={active.voice.replyLanguage}
          onValueChange={setLanguage}
        >
          <SelectTrigger className="w-44" aria-label="Reply language">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LANGUAGES.map((l) => (
              <SelectItem key={l.code} value={l.code}>
                {l.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Live sample reply
        </h3>
        <blockquote className="border-l-4 border-primary pl-3 py-2 pr-3 text-sm italic text-text bg-primary-soft/40 rounded-r-md">
          {reply || "—"}
        </blockquote>
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Non-negotiable rules
        </h3>
        {NON_NEGOTIABLE_RULES.map((rule) => (
          <div
            key={rule}
            className="flex items-center justify-between gap-3 p-2 rounded-md border bg-surface-sunk/40"
          >
            <span className="text-sm flex items-center gap-2">
              <Lock
                className="h-3.5 w-3.5 text-text-muted"
                aria-hidden
              />
              {rule}
            </span>
            <Switch
              checked
              disabled
              aria-label={`${rule} (locked on)`}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
