"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import type { CountryRule, TuningConfig } from "@/lib/types";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

function clone(c: TuningConfig): TuningConfig {
  return JSON.parse(JSON.stringify(c));
}

const FLAGS: Record<string, string> = {
  US: "🇺🇸", GB: "🇬🇧", CA: "🇨🇦", AU: "🇦🇺", DE: "🇩🇪", FR: "🇫🇷",
  BR: "🇧🇷", IN: "🇮🇳", PH: "🇵🇭", NG: "🇳🇬", ZA: "🇿🇦", MX: "🇲🇽",
};

const TIERS = [
  { value: "high" as const, label: "High" },
  { value: "medium" as const, label: "Medium" },
  { value: "low" as const, label: "Low" },
];

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "pt", label: "Portuguese" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "es", label: "Spanish" },
];

function tierClasses(value: CountryRule["priority"]): string {
  if (value === "high") return "bg-primary text-primary-foreground";
  if (value === "medium") return "bg-warning/15 text-warning";
  return "bg-surface-sunk text-text";
}

/**
 * SectionCountries — country cards (2-col grid) with flag, name, priority
 * segmented control, and enable/disable toggle. Plus the reply-language
 * selector below.
 */
export function SectionCountries() {
  const config = useSignalStore((s) => s.config);
  const draftConfig = useSignalStore((s) => s.draftConfig);
  const setDraftConfig = useSignalStore((s) => s.setDraftConfig);
  const active = draftConfig ?? config;

  function setCountry(code: string, patch: Partial<CountryRule>) {
    setDraftConfig({
      ...clone(active),
      countries: active.countries.map((c) =>
        c.code === code ? { ...c, ...patch } : c,
      ),
    });
  }

  function setLanguage(lang: string) {
    setDraftConfig({
      ...clone(active),
      voice: { ...active.voice, replyLanguage: lang },
    });
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {active.countries.map((country) => (
          <div
            key={country.code}
            className={cn(
              "rounded-md border p-3 bg-surface",
              !country.enabled && "opacity-60",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-lg leading-none" aria-hidden>
                  {FLAGS[country.code] ?? "🏳️"}
                </span>
                <div>
                  <div className="text-sm font-medium">{country.name}</div>
                  <div className="text-xs text-text-muted font-mono">
                    {country.code}
                  </div>
                </div>
              </div>
              <Switch
                checked={country.enabled}
                onCheckedChange={(v) =>
                  setCountry(country.code, { enabled: v })
                }
                aria-label={`${country.name} enabled`}
              />
            </div>
            <div
              className="mt-3 inline-flex items-center rounded-md border bg-surface-sunk/40 p-0.5"
              role="radiogroup"
              aria-label={`${country.name} priority`}
            >
              {TIERS.map((tier) => {
                const isActive = country.priority === tier.value;
                return (
                  <button
                    key={tier.value}
                    type="button"
                    role="radio"
                    aria-checked={isActive}
                    onClick={() =>
                      setCountry(country.code, { priority: tier.value })
                    }
                    className={cn(
                      "px-2.5 py-1 text-xs rounded-[5px] transition-colors",
                      isActive
                        ? tierClasses(tier.value)
                        : "text-text-muted hover:text-text",
                    )}
                  >
                    {tier.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] items-start gap-3 rounded-md border p-3 bg-surface">
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
    </div>
  );
}
