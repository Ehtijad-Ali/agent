import type {
  Conversation,
  TuningConfig,
  ActivityEntry,
  KpiSnapshot,
  Status,
} from "./types";
import { DEFAULT_TUNING } from "./constants";
import { generateSeedConversations, generatePreviewSamples } from "./seed";
import { scoreMessage, draftReply } from "./scoring";

/* ============================================================
   mockApi.ts — typed promises with 300–700ms simulated latency.
   Every function is swappable for a real fetch() with zero
   component changes. Replace the body of each function with
   `return fetch('/api/...').then(r => r.json())` to go live.
   ============================================================ */

const STORAGE_KEY = "signal.v1";

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const latency = () => 300 + Math.floor(Math.random() * 400);

interface PersistedState {
  conversations: Conversation[];
  config: TuningConfig;
  activity: ActivityEntry[];
  onboardingComplete: boolean;
  tourComplete: boolean;
}

function defaultState(): PersistedState {
  const config: TuningConfig = JSON.parse(JSON.stringify(DEFAULT_TUNING));
  return {
    conversations: generateSeedConversations(config),
    config,
    activity: [
      {
        id: "act_init",
        timestamp: new Date().toISOString(),
        actor: "system",
        action: "Initial scan completed",
        item: "—",
      },
    ],
    onboardingComplete: false,
    tourComplete: false,
  };
}

function readState(): PersistedState {
  if (typeof window === "undefined") return defaultState();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    const parsed = JSON.parse(raw) as PersistedState;
    // Light validation
    if (!parsed.conversations || !parsed.config) return defaultState();
    return parsed;
  } catch {
    return defaultState();
  }
}

function writeState(state: PersistedState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore quota errors
  }
}

/* ---------------- Conversations ---------------- */

export async function listConversations(): Promise<Conversation[]> {
  await delay(latency());
  return readState().conversations;
}

export async function getConversation(id: string): Promise<Conversation | undefined> {
  await delay(latency());
  return readState().conversations.find((c) => c.id === id);
}

export async function updateConversationStatus(
  id: string,
  status: Status,
  actor = "you",
): Promise<Conversation> {
  await delay(latency());
  const state = readState();
  const idx = state.conversations.findIndex((c) => c.id === id);
  if (idx === -1) throw new Error("Conversation not found");
  const prev = state.conversations[idx];
  const updated: Conversation = {
    ...prev,
    status,
    history: [
      ...prev.history,
      {
        at: new Date().toISOString(),
        actor,
        action: `Status changed to ${status}`,
      },
    ],
  };
  state.conversations[idx] = updated;
  state.activity.unshift({
    id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    timestamp: new Date().toISOString(),
    actor,
    action: `Set status to ${status}`,
    item: prev.id,
    before: prev.status,
    after: status,
  });
  writeState(state);
  return updated;
}

export async function updateReply(
  id: string,
  editedReply: string,
  selectedVariant: number,
  actor = "you",
): Promise<Conversation> {
  await delay(latency());
  const state = readState();
  const idx = state.conversations.findIndex((c) => c.id === id);
  if (idx === -1) throw new Error("Conversation not found");
  const prev = state.conversations[idx];
  const updated: Conversation = {
    ...prev,
    editedReply,
    selectedVariant,
    history: [
      ...prev.history,
      {
        at: new Date().toISOString(),
        actor,
        action: `Edited reply (variant ${selectedVariant + 1})`,
      },
    ],
  };
  state.conversations[idx] = updated;
  state.activity.unshift({
    id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    timestamp: new Date().toISOString(),
    actor,
    action: "Edited reply draft",
    item: prev.id,
    before: prev.editedReply,
    after: editedReply,
  });
  writeState(state);
  return updated;
}

export async function bulkUpdateStatus(
  ids: string[],
  status: Status,
  actor = "you",
): Promise<Conversation[]> {
  await delay(latency());
  const state = readState();
  const updatedList: Conversation[] = [];
  for (const id of ids) {
    const idx = state.conversations.findIndex((c) => c.id === id);
    if (idx === -1) continue;
    const prev = state.conversations[idx];
    const updated: Conversation = {
      ...prev,
      status,
      history: [
        ...prev.history,
        {
          at: new Date().toISOString(),
          actor,
          action: `Bulk status → ${status}`,
        },
      ],
    };
    state.conversations[idx] = updated;
    updatedList.push(updated);
    state.activity.unshift({
      id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      timestamp: new Date().toISOString(),
      actor,
      action: `Bulk set status to ${status}`,
      item: prev.id,
      before: prev.status,
      after: status,
    });
  }
  writeState(state);
  return updatedList;
}

/* ---------------- Config / tuning ---------------- */

export async function getConfig(): Promise<TuningConfig> {
  await delay(latency());
  return readState().config;
}

export async function saveConfig(config: TuningConfig, actor = "you"): Promise<TuningConfig> {
  await delay(latency());
  const state = readState();
  const prev = state.config;
  state.config = config;
  state.activity.unshift({
    id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    timestamp: new Date().toISOString(),
    actor,
    action: "Saved tuning configuration",
    item: "tuning",
    before: JSON.stringify({ voice: prev.voice, thresholds: prev.thresholds }),
    after: JSON.stringify({ voice: config.voice, thresholds: config.thresholds }),
  });
  writeState(state);
  return config;
}

export async function getPreviewSamples(): Promise<Conversation[]> {
  await delay(latency());
  return generatePreviewSamples(readState().config);
}

/** Re-score 8 real samples against an arbitrary config (used by Tuning live preview). */
export function rescoreSamples(config: TuningConfig): Conversation[] {
  return generatePreviewSamples(config);
}

/* ---------------- Playground ---------------- */

export interface AnalyseResult {
  score: number;
  intent: "high" | "medium" | "low" | "not_relevant";
  confidence: "low" | "medium" | "high";
  matchedKeywords: string[];
  contributions: { ruleId: string; label: string; points: number }[];
  riskFlags: string[];
  language: string;
  reply: string;
  replyVariants: { tone: string; text: string }[];
  summary: string;
}

export async function analyseMessage(
  message: string,
  meta: { platform?: string; country?: string; community?: string; url?: string } = {},
): Promise<AnalyseResult> {
  await delay(latency());
  const config = readState().config;
  const result = scoreMessage(message, config, meta.country);
  const replyVariants: { tone: string; text: string }[] = [
    {
      tone: "helpful",
      text: draftReply(
        { message, platform: (meta.platform as never) ?? "discord", community: meta.community ?? "—", country: meta.country ?? "US", matchedKeywords: result.matchedKeywords },
        "helpful",
        config.voice,
      ),
    },
    {
      tone: "concise",
      text: draftReply(
        { message, platform: (meta.platform as never) ?? "discord", community: meta.community ?? "—", country: meta.country ?? "US", matchedKeywords: result.matchedKeywords },
        "concise",
        config.voice,
      ),
    },
    {
      tone: "conversational",
      text: draftReply(
        { message, platform: (meta.platform as never) ?? "discord", community: meta.community ?? "—", country: meta.country ?? "US", matchedKeywords: result.matchedKeywords },
        "conversational",
        config.voice,
      ),
    },
  ];
  const summary =
    result.matchedKeywords.length === 0
      ? "No keywords matched, and the message is not asking for a recommendation."
      : `Matched ${result.matchedKeywords.length} configured keyword${result.matchedKeywords.length === 1 ? "" : "s"}: ${result.matchedKeywords.join(", ")}.`;
  return {
    score: result.score,
    intent: result.intent,
    confidence: result.confidence,
    matchedKeywords: result.matchedKeywords,
    contributions: result.contributions,
    riskFlags: result.riskFlags,
    language: detectLanguage(message),
    reply: replyVariants[0].text,
    replyVariants,
    summary,
  };
}

function detectLanguage(message: string): string {
  const m = message.toLowerCase();
  if (/[áâãàäéêíóôõúç]/.test(message) || /\b(jogo|gratuito|alguém|predição)\b/.test(m)) return "pt";
  if (/[àâçéèêëîïôûùü]/.test(message) || /\b(jeu|gratuit|quelqu'un|pronostic)\b/.test(m)) return "fr";
  if (/[äöüß]/.test(message) || /\b(spiel|kostenlos|jemand|vorhersage)\b/.test(m)) return "de";
  if (/[ñ¿¡]/.test(message) || /\b(juego|gratis|alguien|predicción)\b/.test(m)) return "es";
  return "en";
}

/* ---------------- Activity / audit ---------------- */

export async function listActivity(): Promise<ActivityEntry[]> {
  await delay(latency());
  return readState().activity;
}

export async function logActivity(
  action: string,
  item: string,
  before?: string,
  after?: string,
  actor = "you",
): Promise<void> {
  await delay(latency());
  const state = readState();
  state.activity.unshift({
    id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    timestamp: new Date().toISOString(),
    actor,
    action,
    item,
    before,
    after,
  });
  writeState(state);
}

/* ---------------- Insights / KPI ---------------- */

export async function getKpis(range: "24h" | "7d" | "30d" | "custom"): Promise<KpiSnapshot> {
  await delay(latency());
  const state = readState();
  const now = Date.now();
  const rangeMs =
    range === "24h" ? 86_400_000 : range === "7d" ? 7 * 86_400_000 : 30 * 86_400_000;
  const inRange = state.conversations.filter(
    (c) => now - new Date(c.postedAt).getTime() <= rangeMs,
  );
  const relevant = inRange.filter(
    (c) => c.intent !== "not_relevant" && !c.riskFlags.length,
  );
  const highIntent = inRange.filter((c) => c.intent === "high");
  const awaitingReview = inRange.filter(
    (c) => c.status === "new" || c.status === "awaiting",
  );

  // Build series (hourly for 24h, daily otherwise)
  const buckets = range === "24h" ? 24 : range === "7d" ? 7 : 30;
  const discoveredSeries: { t: string; v: number }[] = [];
  const relevantSeries: { t: string; v: number }[] = [];
  for (let i = buckets - 1; i >= 0; i--) {
    const start = now - i * (rangeMs / buckets);
    const end = start + rangeMs / buckets;
    const t = new Date(start).toISOString();
    const inBucket = state.conversations.filter((c) => {
      const ts = new Date(c.postedAt).getTime();
      return ts >= start && ts < end;
    });
    discoveredSeries.push({
      t,
      v: inBucket.length + Math.floor(Math.random() * 3),
    });
    relevantSeries.push({
      t,
      v: inBucket.filter((c) => c.intent !== "not_relevant").length,
    });
  }

  // Faux deltas (vs the previous equivalent window)
  const factor = 0.85 + Math.random() * 0.4;
  return {
    range,
    discovered: inRange.length,
    relevant: relevant.length,
    highIntent: highIntent.length,
    awaitingReview: awaitingReview.length,
    deltaDiscovered: Math.round((1 - factor) * 100),
    deltaRelevant: Math.round((1 - factor * 1.05) * 100),
    deltaHighIntent: Math.round((1 - factor * 0.9) * 100),
    deltaAwaitingReview: Math.round((1 - factor * 1.1) * 100),
    discoveredSeries,
    relevantSeries,
  };
}

/* ---------------- Onboarding ---------------- */

export async function completeOnboarding(): Promise<void> {
  await delay(latency());
  const state = readState();
  state.onboardingComplete = true;
  writeState(state);
}

export async function completeTour(): Promise<void> {
  await delay(latency());
  const state = readState();
  state.tourComplete = true;
  writeState(state);
}

export async function getOnboardingState(): Promise<{
  onboardingComplete: boolean;
  tourComplete: boolean;
}> {
  await delay(latency());
  const state = readState();
  return {
    onboardingComplete: state.onboardingComplete,
    tourComplete: state.tourComplete,
  };
}

/* ---------------- Reset (for dev / "Reset to defaults") ---------------- */

export async function resetAll(): Promise<void> {
  await delay(latency());
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

export async function runScan(): Promise<{ discovered: number }> {
  await delay(latency() + 200);
  const state = readState();
  state.activity.unshift({
    id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    timestamp: new Date().toISOString(),
    actor: "system",
    action: "Manual scan triggered",
    item: "—",
  });
  writeState(state);
  return { discovered: state.conversations.length };
}
