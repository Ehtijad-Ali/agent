"use client";

import { create } from "zustand";
import type {
  Conversation,
  TuningConfig,
  ActivityEntry,
} from "../lib/types";
import { DEFAULT_TUNING } from "../lib/constants";
import { generateSeedConversations, generatePreviewSamples } from "../lib/seed";

/* ============================================================
   Zustand store — client state for the Signal app.
   Hydrated from localStorage on mount to avoid SSR mismatch.
   ============================================================ */

const STORAGE_KEY = "signal.v1";

interface SignalState {
  // data
  conversations: Conversation[];
  config: TuningConfig;
  activity: ActivityEntry[];
  previewSamples: Conversation[];

  // ui
  currentView: import("../lib/constants").ViewId;
  selectedConversationId: string | null;
  selectedIds: string[];
  range: "24h" | "7d" | "30d" | "custom";
  savedView: string;
  platformFilter: string[];
  intentFilter: string[];
  countryFilter: string[];
  hasRiskFilter: boolean | null;
  scoreRange: [number, number];
  sortKey: "relevance" | "recency" | "intent" | "platform";
  query: string;

  // loading
  loading: boolean;

  // draft config (Tuning) — committed via commitConfig
  draftConfig: TuningConfig | null;
  hasUnsavedChanges: boolean;

  // onboarding
  onboardingComplete: boolean;
  tourComplete: boolean;

  // actions
  hydrate: () => void;
  setConversations: (c: Conversation[]) => void;
  setConfig: (c: TuningConfig) => void;
  setDraftConfig: (c: TuningConfig) => void;
  commitConfig: () => void;
  discardConfig: () => void;
  updateConversation: (c: Conversation) => void;
  bulkUpdate: (ids: string[], patch: Partial<Conversation>) => void;
  pushActivity: (entry: ActivityEntry) => void;
  setActivity: (a: ActivityEntry[]) => void;
  setSelectedConversationId: (id: string | null) => void;
  setSelectedIds: (ids: string[]) => void;
  toggleSelected: (id: string) => void;
  setRange: (r: SignalState["range"]) => void;
  setSavedView: (v: string) => void;
  setPlatformFilter: (v: string[]) => void;
  setIntentFilter: (v: string[]) => void;
  setCountryFilter: (v: string[]) => void;
  setHasRiskFilter: (v: boolean | null) => void;
  setScoreRange: (v: [number, number]) => void;
  setSortKey: (k: SignalState["sortKey"]) => void;
  setQuery: (q: string) => void;
  setLoading: (b: boolean) => void;
  setCurrentView: (v: import("../lib/constants").ViewId) => void;
  setOnboardingComplete: (b: boolean) => void;
  setTourComplete: (b: boolean) => void;
  rescorePreviewSamples: () => void;
  resetAll: () => void;
}

function persistPartial(state: SignalState) {
  if (typeof window === "undefined") return;
  const toStore = {
    conversations: state.conversations,
    config: state.config,
    activity: state.activity,
    onboardingComplete: state.onboardingComplete,
    tourComplete: state.tourComplete,
  };
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore));
  } catch {
    // ignore
  }
}

const initialConfig: TuningConfig = JSON.parse(JSON.stringify(DEFAULT_TUNING));
const initialConversations = generateSeedConversations(initialConfig);
const initialPreviewSamples = generatePreviewSamples(initialConfig);

export const useSignalStore = create<SignalState>((set, get) => ({
  conversations: initialConversations,
  config: initialConfig,
  activity: [
    {
      id: "act_init",
      timestamp: new Date().toISOString(),
      actor: "system",
      action: "Initial scan completed",
      item: "—",
    },
  ],
  previewSamples: initialPreviewSamples,
  selectedConversationId: null,
  selectedIds: [],
  range: "7d",
  savedView: "all",
  currentView: "inbox",
  platformFilter: [],
  intentFilter: [],
  countryFilter: [],
  hasRiskFilter: null,
  scoreRange: [0, 100],
  sortKey: "relevance",
  query: "",
  loading: true,
  draftConfig: null,
  hasUnsavedChanges: false,
  onboardingComplete: false,
  tourComplete: false,

  hydrate: () => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        set({ loading: false });
        return;
      }
      const parsed = JSON.parse(raw);
      set({
        conversations: parsed.conversations ?? initialConversations,
        config: parsed.config ?? initialConfig,
        activity: parsed.activity ?? [],
        onboardingComplete: parsed.onboardingComplete ?? false,
        tourComplete: parsed.tourComplete ?? false,
        previewSamples: generatePreviewSamples(parsed.config ?? initialConfig),
        loading: false,
      });
    } catch {
      set({ loading: false });
    }
  },

  setConversations: (c) => {
    set({ conversations: c });
    persistPartial(get());
  },

  setConfig: (c) => {
    set({ config: c, draftConfig: null, hasUnsavedChanges: false, previewSamples: generatePreviewSamples(c) });
    persistPartial(get());
  },

  setDraftConfig: (c) => {
    set({ draftConfig: c, hasUnsavedChanges: true, previewSamples: generatePreviewSamples(c) });
  },

  commitConfig: () => {
    const draft = get().draftConfig;
    if (!draft) return;
    set({
      config: draft,
      draftConfig: null,
      hasUnsavedChanges: false,
      previewSamples: generatePreviewSamples(draft),
    });
    persistPartial(get());
  },

  discardConfig: () => {
    set({
      draftConfig: null,
      hasUnsavedChanges: false,
      previewSamples: generatePreviewSamples(get().config),
    });
  },

  updateConversation: (c) => {
    set((s) => ({
      conversations: s.conversations.map((x) => (x.id === c.id ? c : x)),
    }));
    persistPartial(get());
  },

  bulkUpdate: (ids, patch) => {
    set((s) => ({
      conversations: s.conversations.map((c) =>
        ids.includes(c.id)
          ? {
              ...c,
              ...patch,
              history: [
                ...c.history,
                {
                  at: new Date().toISOString(),
                  actor: "you",
                  action: `Bulk update: ${Object.keys(patch).join(", ")}`,
                },
              ],
            }
          : c,
      ),
    }));
    persistPartial(get());
  },

  pushActivity: (entry) => {
    set((s) => ({ activity: [entry, ...s.activity] }));
    persistPartial(get());
  },

  setActivity: (a) => {
    set({ activity: a });
    persistPartial(get());
  },

  setSelectedConversationId: (id) => set({ selectedConversationId: id }),
  setSelectedIds: (ids) => set({ selectedIds: ids }),
  toggleSelected: (id) =>
    set((s) => ({
      selectedIds: s.selectedIds.includes(id)
        ? s.selectedIds.filter((x) => x !== id)
        : [...s.selectedIds, id],
    })),

  setRange: (r) => set({ range: r }),
  setSavedView: (v) => set({ savedView: v }),
  setCurrentView: (v) => set({ currentView: v }),
  setPlatformFilter: (v) => set({ platformFilter: v }),
  setIntentFilter: (v) => set({ intentFilter: v }),
  setCountryFilter: (v) => set({ countryFilter: v }),
  setHasRiskFilter: (v) => set({ hasRiskFilter: v }),
  setScoreRange: (v) => set({ scoreRange: v }),
  setSortKey: (k) => set({ sortKey: k }),
  setQuery: (q) => set({ query: q }),
  setLoading: (b) => set({ loading: b }),
  setOnboardingComplete: (b) => {
    set({ onboardingComplete: b });
    persistPartial(get());
  },
  setTourComplete: (b) => {
    set({ tourComplete: b });
    persistPartial(get());
  },

  rescorePreviewSamples: () => {
    const cfg = get().draftConfig ?? get().config;
    set({ previewSamples: generatePreviewSamples(cfg) });
  },

  resetAll: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    const fresh: TuningConfig = JSON.parse(JSON.stringify(DEFAULT_TUNING));
    set({
      conversations: generateSeedConversations(fresh),
      config: fresh,
      draftConfig: null,
      hasUnsavedChanges: false,
      previewSamples: generatePreviewSamples(fresh),
      activity: [
        {
          id: "act_reset",
          timestamp: new Date().toISOString(),
          actor: "system",
          action: "Reset to defaults",
          item: "—",
        },
      ],
      onboardingComplete: false,
      tourComplete: false,
      selectedConversationId: null,
      selectedIds: [],
    });
  },
}));

export function selectById(id: string | null) {
  return (s: SignalState) =>
    s.conversations.find((c) => c.id === id) ?? null;
}
