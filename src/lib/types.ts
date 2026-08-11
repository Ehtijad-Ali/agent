import { z } from "zod";

/* ============================================================
   Signal data model — Zod schemas + TS types
   Every mockApi function returns these; replace with fetch() later.
   ============================================================ */

export const platformSchema = z.enum([
  "discord",
  "telegram",
  "facebook",
  "reddit",
]);
export type Platform = z.infer<typeof platformSchema>;

export const intentSchema = z.enum([
  "high",
  "medium",
  "low",
  "not_relevant",
]);
export type Intent = z.infer<typeof intentSchema>;

export const statusSchema = z.enum([
  "new",
  "awaiting",
  "approved",
  "rejected",
  "snoozed",
  "manually_posted",
  "blocked",
]);
export type Status = z.infer<typeof statusSchema>;

export const riskFlagSchema = z.enum([
  "underage",
  "real_money",
  "spam",
  "negative_keyword",
  "off_topic",
]);
export type RiskFlag = z.infer<typeof riskFlagSchema>;

export const scoreContributionSchema = z.object({
  ruleId: z.string(),
  label: z.string(),
  points: z.number(),
});
export type ScoreContribution = z.infer<typeof scoreContributionSchema>;

export const replyVariantSchema = z.object({
  tone: z.string(),
  text: z.string(),
});
export type ReplyVariant = z.infer<typeof replyVariantSchema>;

export const historyEntrySchema = z.object({
  at: z.string(),
  actor: z.string(),
  action: z.string(),
});
export type HistoryEntry = z.infer<typeof historyEntrySchema>;

export const conversationSchema = z.object({
  id: z.string(),
  platform: platformSchema,
  country: z.string(), // ISO-2
  community: z.string(),
  sourceUrl: z.string().optional(),
  authorPseudonym: z.string(),
  message: z.string(),
  postedAt: z.string(), // ISO
  language: z.string(),
  score: z.number().min(0).max(100),
  intent: intentSchema,
  confidence: z.enum(["low", "medium", "high"]),
  matchedKeywords: z.array(z.string()),
  contributions: z.array(scoreContributionSchema),
  summary: z.string(),
  riskFlags: z.array(riskFlagSchema),
  status: statusSchema,
  replyVariants: z.array(replyVariantSchema),
  selectedVariant: z.number(),
  editedReply: z.string().optional(),
  history: z.array(historyEntrySchema),
});
export type Conversation = z.infer<typeof conversationSchema>;

/* ---------------- Tuning / config ---------------- */

export const matchTypeSchema = z.enum(["broad", "exact", "phrase"]);
export type MatchType = z.infer<typeof matchTypeSchema>;

export const keywordRuleSchema = z.object({
  id: z.string(),
  term: z.string(),
  matchType: matchTypeSchema,
  priority: z.number().min(1).max(5),
  weight: z.number(),
  hits7d: z.number(),
});
export type KeywordRule = z.infer<typeof keywordRuleSchema>;

export const negativeKeywordRuleSchema = z.object({
  id: z.string(),
  term: z.string(),
  matchType: matchTypeSchema,
  weight: z.number(),
  hits7d: z.number(),
});
export type NegativeKeywordRule = z.infer<typeof negativeKeywordRuleSchema>;

export const countryRuleSchema = z.object({
  code: z.string(), // ISO-2
  name: z.string(),
  priority: z.enum(["high", "medium", "low"]),
  enabled: z.boolean(),
});
export type CountryRule = z.infer<typeof countryRuleSchema>;

export const thresholdsSchema = z.object({
  notRelevant: z.number().min(0).max(100),
  low: z.number().min(0).max(100),
  medium: z.number().min(0).max(100),
  high: z.number().min(0).max(100),
});
export type Thresholds = z.infer<typeof thresholdsSchema>;

export const voiceConfigSchema = z.object({
  friendliness: z.number().min(0).max(100),
  helpfulness: z.number().min(0).max(100),
  formality: z.number().min(0).max(100),
  ctaStrength: z.number().min(0).max(100),
  emoji: z.number().min(0).max(100),
  maxLength: z.number().min(80).max(600),
  replyLanguage: z.string(),
});
export type VoiceConfig = z.infer<typeof voiceConfigSchema>;

export const scoringConfigSchema = z.object({
  boosts: z.object({
    asksRecommendation: z.number(),
    mentionsNoDeposit: z.number(),
    mentionsFree: z.number(),
    mentionsGame: z.number(),
    mentionsSocial: z.number(),
    highPriorityCountry: z.number(),
    recentPost: z.number(),
  }),
  penalties: z.object({
    negativeKeyword: z.number(),
    offTopic: z.number(),
    promotional: z.number(),
    lowPriorityCountry: z.number(),
  }),
});
export type ScoringConfig = z.infer<typeof scoringConfigSchema>;

export const tuningConfigSchema = z.object({
  keywords: z.array(keywordRuleSchema),
  negativeKeywords: z.array(negativeKeywordRuleSchema),
  countries: z.array(countryRuleSchema),
  thresholds: thresholdsSchema,
  voice: voiceConfigSchema,
  scoring: scoringConfigSchema,
  rateCaps: z.object({
    perPlatformPerHour: z.number(),
    dailyApprovedCeiling: z.number(),
  }),
});
export type TuningConfig = z.infer<typeof tuningConfigSchema>;

export const presetSchema = z.object({
  id: z.string(),
  name: z.string(),
  createdAt: z.string(),
  config: tuningConfigSchema,
});
export type Preset = z.infer<typeof presetSchema>;

/* ---------------- Activity / audit ---------------- */

export const activityEntrySchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  actor: z.string(),
  action: z.string(),
  item: z.string(),
  before: z.string().optional(),
  after: z.string().optional(),
});
export type ActivityEntry = z.infer<typeof activityEntrySchema>;

/* ---------------- Insights ---------------- */

export const kpiSnapshotSchema = z.object({
  range: z.enum(["24h", "7d", "30d", "custom"]),
  discovered: z.number(),
  relevant: z.number(),
  highIntent: z.number(),
  awaitingReview: z.number(),
  deltaDiscovered: z.number(),
  deltaRelevant: z.number(),
  deltaHighIntent: z.number(),
  deltaAwaitingReview: z.number(),
  discoveredSeries: z.array(z.object({ t: z.string(), v: z.number() })),
  relevantSeries: z.array(z.object({ t: z.string(), v: z.number() })),
});
export type KpiSnapshot = z.infer<typeof kpiSnapshotSchema>;
