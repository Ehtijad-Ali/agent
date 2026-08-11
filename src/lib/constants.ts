import type { Platform, RiskFlag, Intent, Status } from "./types";

/* ============================================================
   Static reference data for the Signal app
   ============================================================ */

export const COUNTRIES = [
  { code: "US", name: "United States", flag: "🇺🇸" },
  { code: "GB", name: "United Kingdom", flag: "🇬🇧" },
  { code: "CA", name: "Canada", flag: "🇨🇦" },
  { code: "AU", name: "Australia", flag: "🇦🇺" },
  { code: "DE", name: "Germany", flag: "🇩🇪" },
  { code: "FR", name: "France", flag: "🇫🇷" },
  { code: "BR", name: "Brazil", flag: "🇧🇷" },
  { code: "IN", name: "India", flag: "🇮🇳" },
  { code: "PH", name: "Philippines", flag: "🇵🇭" },
  { code: "NG", name: "Nigeria", flag: "🇳🇬" },
  { code: "ZA", name: "South Africa", flag: "🇿🇦" },
  { code: "MX", name: "Mexico", flag: "🇲🇽" },
] as const;

export const PLATFORMS: Record<
  Platform,
  { label: string; glyph: string; color: string; tosUrl: string }
> = {
  discord: {
    label: "Discord",
    glyph: "🎮",
    color: "#5865F2",
    tosUrl: "https://discord.com/terms",
  },
  telegram: {
    label: "Telegram",
    glyph: "✈️",
    color: "#26A5E4",
    tosUrl: "https://telegram.org/tos",
  },
  facebook: {
    label: "Facebook",
    glyph: "📘",
    color: "#1877F2",
    tosUrl: "https://www.facebook.com/terms.php",
  },
  reddit: {
    label: "Reddit",
    glyph: "👽",
    color: "#FF4500",
    tosUrl: "https://www.redditinc.com/policies/user-agreement",
  },
};

export const INTENT_META: Record<
  Intent,
  { label: string; min: number; max: number }
> = {
  high: { label: "High intent", min: 80, max: 100 },
  medium: { label: "Medium intent", min: 60, max: 79 },
  low: { label: "Low intent", min: 40, max: 59 },
  not_relevant: { label: "Not relevant", min: 0, max: 39 },
};

export const RISK_META: Record<
  RiskFlag,
  { label: string; icon: string; description: string }
> = {
  underage: {
    label: "Underage author",
    icon: "shield-alert",
    description:
      "Message indicates the author may be under 18. Reply generation auto-blocked.",
  },
  real_money: {
    label: "Real-money gambling request",
    icon: "shield-x",
    description:
      "Author is asking about real-money gambling. This product is free-to-play only.",
  },
  spam: {
    label: "Spam / promotional bait",
    icon: "shield-x",
    description:
      "Message looks like spam or promotional bait. Auto-rejected.",
  },
  negative_keyword: {
    label: "Negative keyword",
    icon: "shield-minus",
    description: "Message contains a configured negative keyword.",
  },
  off_topic: {
    label: "Off-topic",
    icon: "shield-minus",
    description: "Message is off-topic for this brand.",
  },
};

export const STATUS_META: Record<
  Status,
  { label: string; tone: "neutral" | "primary" | "success" | "warning" | "risk" }
> = {
  new: { label: "New", tone: "neutral" },
  awaiting: { label: "Awaiting review", tone: "warning" },
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Rejected", tone: "risk" },
  snoozed: { label: "Snoozed 24h", tone: "neutral" },
  manually_posted: { label: "Manually posted", tone: "success" },
  blocked: { label: "Blocked", tone: "risk" },
};

export const SAVED_VIEWS = [
  { id: "all", label: "All conversations" },
  { id: "needs_review", label: "Needs review" },
  { id: "high_intent", label: "High intent" },
  { id: "risk_flagged", label: "Risk flagged" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
  { id: "snoozed", label: "Snoozed" },
] as const;

export const NAV_ITEMS = [
  { id: "inbox", label: "Inbox", icon: "inbox", shortcut: "G I" },
  { id: "triage", label: "Triage", icon: "layers", shortcut: "G T" },
  { id: "insights", label: "Insights", icon: "bar-chart-3", shortcut: "G N" },
  { id: "playground", label: "Playground", icon: "flask-conical", shortcut: "G P" },
  { id: "tuning", label: "Tuning", icon: "sliders-horizontal", shortcut: "G U" },
  { id: "safety", label: "Safety", icon: "shield-check", shortcut: "G S" },
  { id: "activity", label: "Activity", icon: "history", shortcut: "G A" },
] as const;

export type ViewId = (typeof NAV_ITEMS)[number]["id"];

export const VOICE_TONES = [
  { id: "helpful", label: "Helpful" },
  { id: "concise", label: "Concise" },
  { id: "conversational", label: "Conversational" },
] as const;

/* Default tuning — used for first run and "Reset to defaults" */
export const DEFAULT_TUNING = {
  keywords: [
    { id: "kw1", term: "free game", matchType: "phrase", priority: 5, weight: 14, hits7d: 142 },
    { id: "kw2", term: "prediction game", matchType: "phrase", priority: 5, weight: 16, hits7d: 98 },
    { id: "kw3", term: "no deposit", matchType: "phrase", priority: 5, weight: 18, hits7d: 76 },
    { id: "kw4", term: "play without depositing", matchType: "phrase", priority: 4, weight: 15, hits7d: 41 },
    { id: "kw5", term: "free to play", matchType: "phrase", priority: 4, weight: 12, hits7d: 88 },
    { id: "kw6", term: "social prediction", matchType: "phrase", priority: 4, weight: 14, hits7d: 35 },
    { id: "kw7", term: "recommend a game", matchType: "phrase", priority: 3, weight: 12, hits7d: 52 },
    { id: "kw8", term: "anyone know a game", matchType: "phrase", priority: 3, weight: 10, hits7d: 47 },
    { id: "kw9", term: "betting game", matchType: "broad", priority: 3, weight: 8, hits7d: 64 },
    { id: "kw10", term: "prediction", matchType: "broad", priority: 2, weight: 5, hits7d: 231 },
    { id: "kw11", term: "fun game", matchType: "phrase", priority: 2, weight: 6, hits7d: 119 },
    { id: "kw12", term: "free betting", matchType: "phrase", priority: 3, weight: 10, hits7d: 33 },
  ],
  negativeKeywords: [
    { id: "nk1", term: "real money", matchType: "phrase", weight: -25, hits7d: 28 },
    { id: "nk2", term: "deposit required", matchType: "phrase", weight: -20, hits7d: 14 },
    { id: "nk3", term: "crypto", matchType: "broad", weight: -15, hits7d: 22 },
    { id: "nk4", term: "withdrawal", matchType: "broad", weight: -18, hits7d: 19 },
    { id: "nk5", term: "under 18", matchType: "phrase", weight: -100, hits7d: 3 },
    { id: "nk6", term: "gambling site", matchType: "phrase", weight: -22, hits7d: 12 },
  ],
  countries: [
    { code: "US", name: "United States", priority: "high", enabled: true },
    { code: "GB", name: "United Kingdom", priority: "high", enabled: true },
    { code: "CA", name: "Canada", priority: "high", enabled: true },
    { code: "AU", name: "Australia", priority: "medium", enabled: true },
    { code: "DE", name: "Germany", priority: "medium", enabled: true },
    { code: "FR", name: "France", priority: "medium", enabled: true },
    { code: "BR", name: "Brazil", priority: "low", enabled: true },
    { code: "IN", name: "India", priority: "low", enabled: true },
    { code: "PH", name: "Philippines", priority: "low", enabled: true },
    { code: "NG", name: "Nigeria", priority: "low", enabled: false },
    { code: "ZA", name: "South Africa", priority: "low", enabled: false },
    { code: "MX", name: "Mexico", priority: "low", enabled: true },
  ],
  thresholds: { notRelevant: 0, low: 40, medium: 60, high: 80 },
  voice: {
    friendliness: 70,
    helpfulness: 80,
    formality: 35,
    ctaStrength: 55,
    emoji: 20,
    maxLength: 280,
    replyLanguage: "en",
  },
  scoring: {
    boosts: {
      asksRecommendation: 14,
      mentionsNoDeposit: 18,
      mentionsFree: 12,
      mentionsGame: 10,
      mentionsSocial: 8,
      highPriorityCountry: 6,
      recentPost: 4,
    },
    penalties: {
      negativeKeyword: -15,
      offTopic: -20,
      promotional: -25,
      lowPriorityCountry: -4,
    },
  },
  rateCaps: { perPlatformPerHour: 5, dailyApprovedCeiling: 30 },
} as const;

/* Non-negotiable rules shown as locked toggles in Tuning → Reply voice */
export const NON_NEGOTIABLE_RULES = [
  "Always disclose brand connection",
  "Always include 'free-to-play, not real money'",
  "Never post autonomously",
  "Never DM authors",
  "One reply per person, ever",
] as const;
