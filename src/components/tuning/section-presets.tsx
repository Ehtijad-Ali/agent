"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import type { Preset, TuningConfig } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Save, FileDiff, Trash2, Upload, History } from "lucide-react";
import { cn } from "@/lib/utils";

const KEY = "signal.presets.v1";

function loadPresets(): Preset[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? (arr as Preset[]) : [];
  } catch {
    return [];
  }
}

function savePresets(p: Preset[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* ignore quota errors */
  }
}

/**
 * SectionPresets — save the current draft (or committed config) as a named
 * preset, list saved presets with Load / Diff / Roll-back actions, and a
 * diff dialog comparing voice + thresholds against the current config.
 * Storage: localStorage `signal.presets.v1`.
 */
export function SectionPresets() {
  const config = useSignalStore((s) => s.config);
  const draftConfig = useSignalStore((s) => s.draftConfig);
  const setDraftConfig = useSignalStore((s) => s.setDraftConfig);
  const active = draftConfig ?? config;

  const [presets, setPresets] = React.useState<Preset[]>([]);
  const [nameOpen, setNameOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [diffPreset, setDiffPreset] = React.useState<Preset | null>(null);

  React.useEffect(() => {
    setPresets(loadPresets());
  }, []);

  function persist(next: Preset[]) {
    setPresets(next);
    savePresets(next);
  }

  function savePreset() {
    if (!name.trim()) return;
    const p: Preset = {
      id: `preset_${Date.now()}`,
      name: name.trim(),
      createdAt: new Date().toISOString(),
      config: JSON.parse(JSON.stringify(active)),
    };
    persist([p, ...presets]);
    setName("");
    setNameOpen(false);
  }

  function loadPreset(p: Preset) {
    setDraftConfig(JSON.parse(JSON.stringify(p.config)));
  }

  function deletePreset(id: string) {
    persist(presets.filter((p) => p.id !== id));
  }

  return (
    <div className="space-y-3">
      <Button size="sm" onClick={() => setNameOpen(true)}>
        <Save className="h-3.5 w-3.5" aria-hidden /> Save current as preset
      </Button>

      {presets.length === 0 ? (
        <p className="text-sm text-text-muted">
          No saved presets yet. Save your current config to reuse or roll
          back to it later.
        </p>
      ) : (
        <ul className="space-y-2">
          {presets.map((p) => (
            <li
              key={p.id}
              className="flex flex-wrap items-center gap-2 p-3 rounded-md border bg-surface"
            >
              <div className="flex-1 min-w-[120px]">
                <div className="text-sm font-medium truncate">{p.name}</div>
                <div className="text-xs text-text-muted">
                  {new Date(p.createdAt).toLocaleString()}
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadPreset(p)}
                aria-label={`Load preset ${p.name}`}
              >
                <Upload className="h-3.5 w-3.5" aria-hidden /> Load
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDiffPreset(p)}
                aria-label={`Diff preset ${p.name}`}
              >
                <FileDiff className="h-3.5 w-3.5" aria-hidden /> Diff
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => loadPreset(p)}
                aria-label={`Roll back to preset ${p.name}`}
              >
                <History className="h-3.5 w-3.5" aria-hidden /> Roll back
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => deletePreset(p.id)}
                aria-label={`Delete preset ${p.name}`}
              >
                <Trash2 className="h-3.5 w-3.5 text-risk" aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={nameOpen} onOpenChange={setNameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save preset</DialogTitle>
            <DialogDescription>
              Give your current config a memorable name.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Aggressive discovery"
            aria-label="Preset name"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                savePreset();
              }
            }}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setNameOpen(false)}>
              Cancel
            </Button>
            <Button onClick={savePreset} disabled={!name.trim()}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={diffPreset !== null}
        onOpenChange={(o) => {
          if (!o) setDiffPreset(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Diff: {diffPreset?.name}</DialogTitle>
            <DialogDescription>
              Voice and thresholds vs current config.
            </DialogDescription>
          </DialogHeader>
          {diffPreset && (
            <PresetDiff current={active} preset={diffPreset.config} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

const VOICE_KEYS = [
  "friendliness",
  "helpfulness",
  "formality",
  "ctaStrength",
  "emoji",
  "maxLength",
] as const;
const THRESHOLD_KEYS = [
  "notRelevant",
  "low",
  "medium",
  "high",
] as const;

function PresetDiff({
  current,
  preset,
}: {
  current: TuningConfig;
  preset: TuningConfig;
}) {
  const rows: { label: string; cur: number; pre: number }[] = [];
  VOICE_KEYS.forEach((k) =>
    rows.push({
      label: `Voice · ${k}`,
      cur: current.voice[k] as number,
      pre: preset.voice[k] as number,
    }),
  );
  THRESHOLD_KEYS.forEach((k) =>
    rows.push({
      label: `Threshold · ${k}`,
      cur: current.thresholds[k],
      pre: preset.thresholds[k],
    }),
  );
  return (
    <div className="max-h-80 overflow-y-auto rounded-md border">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-text-muted bg-surface-sunk/40">
            <th className="text-left p-2 font-medium">Field</th>
            <th className="text-right p-2 font-medium">Current</th>
            <th className="text-right p-2 font-medium">Preset</th>
            <th className="text-right p-2 font-medium">Δ</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const d = r.pre - r.cur;
            return (
              <tr key={r.label} className="border-t">
                <td className="p-2">{r.label}</td>
                <td className="p-2 text-right font-mono tabular-nums">
                  {r.cur}
                </td>
                <td className="p-2 text-right font-mono tabular-nums">
                  {r.pre}
                </td>
                <td
                  className={cn(
                    "p-2 text-right font-mono tabular-nums",
                    d > 0
                      ? "text-success"
                      : d < 0
                        ? "text-risk"
                        : "text-text-muted",
                  )}
                >
                  {d > 0 ? "+" : ""}
                  {d}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
