"use client";

import { create } from "zustand";
import type {
  Conversation,
  TuningConfig,
  ActivityEntry,
} from "../lib/types";
import { DEFAULT_TUNING } from "../lib/constants";
import { generatePreviewSamples } from "../lib/seed";
import * as api from "../lib/api";

/* ============================================================
   Zustand store — client state for the Signal app.

   Conversations, config and activity come from the backend. Only UI
   preferences are kept in localStorage: persisting server data there
   meant a stale copy could outlive the row it described.

   Preview samples in Tuning are still generated and scored client-side.
   That is deliberate — they are a fixed synthetic set whose whole job is
   to show the effect of a config change instantly (spec §21). They are
   not discovered leads and never appear in the Inbox.
   ============================================================ */

// v2: v1 held seeded conversations. Bumping the key means an old browser
// profile is ignored rather than resurrecting fake data next to real rows.
const STORAGE_KEY = "signal.v2";

interface SignalState {
  // data
  conversations: Conversation[];
  config: TuningConfig;
  activity: ActivityEntry[];
  previewSamples: Conversation[];
  /** Live credential status per platform (spec §29). Never includes tokens. */
  platforms: api.PlatformStatus[];
  /** When the most recent scan finished, ISO. Null until one has. */
  lastScanAt: string | null;
  scanning: boolean;

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
  /** Set when the backend is unreachable, so screens can say so. */
  error: string | null;

  // draft config (Tuning) — committed via commitConfig
  draftConfig: TuningConfig | null;
  hasUnsavedChanges: boolean;

  // onboarding
  onboardingComplete: boolean;
  tourComplete: boolean;

  // actions
  hydrate: () => void;
  refresh: () => Promise<void>;
  refreshActivityOnly: () => Promise<void>;
  runScan: () => Promise<api.ScanResult | null>;
  sendReply: (id: string) => Promise<api.SendResult | string>;
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

/** Only UI preferences. Server data is fetched, never cached here. */
function persistPreferences(state: SignalState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        onboardingComplete: state.onboardingComplete,
        tourComplete: state.tourComplete,
      }),
    );
  } catch {
    // Private mode or blocked storage: preferences simply do not persist.
  }
}

const initialConfig: TuningConfig = JSON.parse(JSON.stringify(DEFAULT_TUNING));

let hydrating = false;

export const useSignalStore = create<SignalState>((set, get) => ({
  // Empty until the first fetch resolves. The screens already render an empty
  // state, which is the honest thing to show before any data has arrived.
  conversations: [],
  config: initialConfig,
  activity: [],
  previewSamples: generatePreviewSamples(initialConfig),
  platforms: [],
  lastScanAt: null,
  scanning: false,
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
  error: null,
  draftConfig: null,
  hasUnsavedChanges: false,
  onboardingComplete: false,
  tourComplete: false,

  hydrate: () => {
    if (typeof window === "undefined") return;
    // Several views call hydrate() on mount; only the first should fetch.
    if (hydrating) return;
    hydrating = true;

    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        set({
          onboardingComplete: parsed.onboardingComplete ?? false,
          tourComplete: parsed.tourComplete ?? false,
        });
      }
    } catch {
      // Ignore unreadable preferences; the fetch below still runs.
    }

    void get().refresh();
  },

  refresh: async () => {
    try {
      const [conversations, config, activity, platforms] = await Promise.all([
        api.listConversations(),
        api.getConfig(),
        api.listActivity(),
        // A platform probe failing must not blank the Inbox, so it degrades to
        // an empty list rather than rejecting the whole load.
        api.getPlatformStatus().catch(() => []),
      ]);
      set({
        conversations,
        config,
        activity,
        platforms,
        previewSamples: generatePreviewSamples(config),
        loading: false,
        error: null,
      });
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : "Could not load data.";
      // Leave whatever is already on screen in place; replacing it with nothing
      // would make a transient blip look like an empty inbox.
      set({ loading: false, error: message });
    }
  },

  /**
   * Refetch just the audit log, after a write the server logged.
   *
   * Cheaper than a full refresh, and it keeps the Activity screen truthful
   * without re-pulling every conversation on each triage keystroke.
   */
  refreshActivityOnly: async () => {
    try {
      set({ activity: await api.listActivity() });
    } catch {
      // The write itself succeeded; a stale log is not worth an error banner.
    }
  },

  runScan: async () => {
    if (get().scanning) return null;
    set({ scanning: true });
    try {
      const result = await api.runScan();
      await get().refresh();
      set({ lastScanAt: new Date().toISOString() });
      return result;
    } catch (cause) {
      set({ error: cause instanceof Error ? cause.message : "Scan failed." });
      return null;
    } finally {
      set({ scanning: false });
    }
  },

  /**
   * Post the approved reply to the platform.
   *
   * Returns the result, or the refusal message as a string. Deliberately not
   * optimistic: nothing on screen changes until the platform has confirmed the
   * message, because showing "replied" for a send that failed would be a lie
   * about something already public.
   */
  sendReply: async (id) => {
    try {
      const result = await api.sendReply(id);
      set((state) => ({
        conversations: state.conversations.map((c) =>
          c.id === result.conversation.id ? result.conversation : c,
        ),
      }));
      await get().refreshActivityOnly();
      return result;
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : "Could not send the reply.";
      set({ error: message });
      return message;
    }
  },

  setConversations: (c) => set({ conversations: c }),

  setConfig: (c) => {
    set({
      config: c,
      draftConfig: null,
      hasUnsavedChanges: false,
      previewSamples: generatePreviewSamples(c),
    });
    void api.saveConfig(c).catch((cause) => {
      set({ error: cause instanceof Error ? cause.message : "Could not save config." });
    });
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
    void api
      .saveConfig(draft)
      .then(() => get().refreshActivityOnly())
      .catch((cause) => {
        set({
          error: cause instanceof Error ? cause.message : "Could not save config.",
        });
      });
  },

  discardConfig: () => {
    set({
      draftConfig: null,
      hasUnsavedChanges: false,
      previewSamples: generatePreviewSamples(get().config),
    });
  },

  /**
   * Optimistic local update, then persist whatever actually changed.
   *
   * Components hand over a whole Conversation, so the change has to be
   * recovered by diffing against the row we hold. Status goes to its §18 verb
   * endpoint; reply edits go to /edit. On failure the previous row is put back,
   * because a triage decision that silently did not save is worse than a
   * visible error.
   */
  updateConversation: (next) => {
    const previous = get().conversations.find((c) => c.id === next.id);
    set((s) => ({
      conversations: s.conversations.map((x) => (x.id === next.id ? next : x)),
    }));
    if (!previous) return;

    const statusChanged = previous.status !== next.status;
    const replyChanged =
      previous.editedReply !== next.editedReply ||
      previous.selectedVariant !== next.selectedVariant;

    const calls: Promise<Conversation>[] = [];
    if (statusChanged) calls.push(api.setStatus(next.id, next.status));
    if (replyChanged) {
      calls.push(
        api.editReply(next.id, {
          editedReply: next.editedReply ?? null,
          selectedVariant: next.selectedVariant,
        }),
      );
    }
    if (calls.length === 0) return;

    void Promise.all(calls)
      .then((results) => {
        // The last response is the freshest; it carries the server's history.
        const authoritative = results[results.length - 1];
        set((s) => ({
          conversations: s.conversations.map((x) =>
            x.id === authoritative.id ? authoritative : x,
          ),
        }));
        return get().refreshActivityOnly();
      })
      .catch((cause) => {
        set((s) => ({
          conversations: s.conversations.map((x) =>
            x.id === previous.id ? previous : x,
          ),
          error: cause instanceof Error ? cause.message : "Could not save change.",
        }));
      });
  },

  bulkUpdate: (ids, patch) => {
    const update = get().updateConversation;
    for (const conversation of get().conversations) {
      if (ids.includes(conversation.id)) {
        update({ ...conversation, ...patch });
      }
    }
  },

  /** Local-only echo. The authoritative row is written server-side. */
  pushActivity: (entry) => set((s) => ({ activity: [entry, ...s.activity] })),

  setActivity: (a) => set({ activity: a }),

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
    persistPreferences(get());
  },
  setTourComplete: (b) => {
    set({ tourComplete: b });
    persistPreferences(get());
  },

  rescorePreviewSamples: () => {
    const cfg = get().draftConfig ?? get().config;
    set({ previewSamples: generatePreviewSamples(cfg) });
  },

  /**
   * Clears local UI state and reloads from the server.
   *
   * It does NOT delete conversations: they are discovered records, and a
   * "reset to defaults" button in the UI must not silently destroy the audit
   * trail. Wiping data is a backend operation, done deliberately.
   */
  resetAll: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    set({
      draftConfig: null,
      hasUnsavedChanges: false,
      onboardingComplete: false,
      tourComplete: false,
      selectedConversationId: null,
      selectedIds: [],
      error: null,
    });
    void get().refresh();
  },
}));

export function selectById(id: string | null) {
  return (s: SignalState) =>
    s.conversations.find((c) => c.id === id) ?? null;
}
