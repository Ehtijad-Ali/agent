"use client";

import * as React from "react";
import { Eraser, FlaskConical, Sparkles, HelpCircle, ShieldAlert } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { COUNTRIES } from "@/lib/constants";
import type { Platform } from "@/lib/types";

export const SAMPLES = [
  {
    id: "high",
    label: "High intent",
    icon: Sparkles,
    message:
      "Anyone know a good free prediction game I can play with friends? Looking for something where I don't have to deposit any money, just pure fun.",
  },
  {
    id: "ambiguous",
    label: "Ambiguous",
    icon: HelpCircle,
    message:
      "What's a fun game to play this weekend with mates online?",
  },
  {
    id: "risky",
    label: "Risky",
    icon: ShieldAlert,
    message:
      "I'm 15 and looking for a real money gambling site, anyone got a recommendation?",
  },
] as const;

export interface PlaygroundForm {
  message: string;
  platform: Platform;
  country: string;
  community: string;
  url: string;
}

export function PlaygroundInput({
  form,
  onFormChange,
  onAnalyse,
  onClear,
  loading,
}: {
  form: PlaygroundForm;
  onFormChange: (patch: Partial<PlaygroundForm>) => void;
  onAnalyse: () => void;
  onClear: () => void;
  loading: boolean;
}) {
  const charCount = form.message.length;

  return (
    <div className="space-y-4">
      {/* Message */}
      <div className="space-y-1.5">
        <div className="flex items-baseline justify-between">
          <Label
            htmlFor="pg-message"
            className="text-xs font-semibold uppercase tracking-wide text-text-muted"
          >
            Message
          </Label>
          <span
            className="text-xs text-text-muted font-mono tabular-nums"
            aria-live="polite"
          >
            {charCount} chars
          </span>
        </div>
        <Textarea
          id="pg-message"
          value={form.message}
          onChange={(e) => onFormChange({ message: e.target.value })}
          rows={8}
          placeholder="Paste or type a message you want to analyse…"
          className="resize-y min-h-[160px] leading-relaxed"
          aria-describedby="pg-message-help"
        />
        <p id="pg-message-help" className="text-[11px] text-text-muted">
          Press <kbd className="font-mono text-[10px]">⌘/Ctrl + ↵</kbd> to analyse.
        </p>
      </div>

      {/* Sample buttons */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Try a sample
        </p>
        <div className="grid grid-cols-3 gap-2">
          {SAMPLES.map((s) => {
            const Icon = s.icon;
            return (
              <Button
                key={s.id}
                variant="outline"
                size="sm"
                className="justify-start gap-1.5 h-auto py-1.5 px-2.5 text-xs"
                aria-label={`Load ${s.label} sample message`}
                onClick={() => onFormChange({ message: s.message })}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
                <span className="truncate">{s.label}</span>
              </Button>
            );
          })}
        </div>
      </div>

      {/* Meta grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label
            htmlFor="pg-platform"
            className="text-xs font-semibold uppercase tracking-wide text-text-muted"
          >
            Platform
          </Label>
          <Select
            value={form.platform}
            onValueChange={(v) => onFormChange({ platform: v as Platform })}
          >
            <SelectTrigger id="pg-platform" className="w-full" aria-label="Platform">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Platform</SelectLabel>
                <SelectItem value="discord">🎮 Discord</SelectItem>
                <SelectItem value="telegram">✈️ Telegram</SelectItem>
                <SelectItem value="facebook">📘 Facebook</SelectItem>
                <SelectItem value="reddit">👽 Reddit</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label
            htmlFor="pg-country"
            className="text-xs font-semibold uppercase tracking-wide text-text-muted"
          >
            Country
          </Label>
          <Select
            value={form.country}
            onValueChange={(v) => onFormChange({ country: v })}
          >
            <SelectTrigger id="pg-country" className="w-full" aria-label="Country">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Country</SelectLabel>
                {COUNTRIES.map((c) => (
                  <SelectItem key={c.code} value={c.code}>
                    <span aria-hidden>{c.flag}</span>
                    <span>{c.name}</span>
                    <span className="text-text-muted font-mono text-[10px]">
                      {c.code}
                    </span>
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label
            htmlFor="pg-community"
            className="text-xs font-semibold uppercase tracking-wide text-text-muted"
          >
            Community
          </Label>
          <Input
            id="pg-community"
            value={form.community}
            onChange={(e) => onFormChange({ community: e.target.value })}
            placeholder="e.g. r/predictiongames"
            aria-label="Community"
          />
        </div>

        <div className="space-y-1.5">
          <Label
            htmlFor="pg-url"
            className="text-xs font-semibold uppercase tracking-wide text-text-muted"
          >
            Reply URL
          </Label>
          <Input
            id="pg-url"
            value={form.url}
            onChange={(e) => onFormChange({ url: e.target.value })}
            placeholder="https://joinallbettors.example"
            type="url"
            aria-label="Reply URL"
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1">
        <Button
          onClick={onAnalyse}
          disabled={loading || form.message.trim().length === 0}
          className="flex-1"
          aria-label="Analyse the message"
        >
          <FlaskConical className="h-4 w-4" aria-hidden />
          {loading ? "Analysing…" : "Analyse"}
        </Button>
        <Button
          variant="ghost"
          onClick={onClear}
          disabled={loading}
          aria-label="Clear the input and results"
        >
          <Eraser className="h-4 w-4" aria-hidden />
          Clear
        </Button>
      </div>
    </div>
  );
}
