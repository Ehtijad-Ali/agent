import type {
  Conversation,
  Intent,
  ScoreContribution,
  RiskFlag,
  TuningConfig,
} from "./types";
import { INTENT_META } from "./constants";

/* ============================================================
   Signal Scoring Engine
   ------------------------------------------------------------
   Robust keyword matcher + contribution breakdown.
   Used by: mockApi (seed scoring), Tuning live preview,
   Playground analyse(), and the unit tests.

   Design goals:
   - Case-insensitive
   - Punctuation-stripped
   - Whitespace-normalised
   - Stemming (light suffix-stripping: -ing, -ed, -s, -es, -ies→y)
   - Near-phrase matching (edit distance ≤ 1 for phrase matches)
   - Partial matches at reduced weight (broad matchType)

   A score is computed from contributions (boosts + penalties),
   then clamped to 0..100. Intent band is derived from thresholds.
   ============================================================ */

const STOP_WORDS = new Set([
  "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
  "to", "of", "in", "on", "at", "for", "with", "without", "and", "or",
  "but", "if", "then", "than", "so", "as", "by", "this", "that", "these",
  "those", "i", "you", "we", "they", "he", "she", "it", "my", "your",
  "our", "their", "his", "her", "its", "me", "him", "them", "us",
  "do", "does", "did", "have", "has", "had", "will", "would", "can",
  "could", "should", "may", "might", "must", "shall", "any", "some",
  "no", "not", "very", "too", "also", "just", "only", "really", "anyone",
  "someone", "know", "looking", "find",
  // common prepositions & adverbs
  "about", "above", "across", "after", "against", "along", "among", "around",
  "before", "behind", "below", "beneath", "beside", "between", "beyond",
  "during", "except", "from", "inside", "into", "near", "off", "onto",
  "outside", "over", "through", "throughout", "toward", "under", "until",
  "up", "upon", "within", "out", "down", "again", "more", "most",
  "other", "such", "own", "same", "few", "all", "both", "each",
  "get", "got", "make", "made", "go", "goes", "went",
]);

/** Normalise text for matching: lowercase, strip punctuation, collapse whitespace. */
export function normaliseText(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Light stemmer — strips common English suffixes. */
export function stem(word: string): string {
  let w = word.toLowerCase().trim();
  if (w.length <= 3) return w;
  // -ies → -y  (e.g. "countries" → "country")
  if (w.endsWith("ies") && w.length > 4) return w.slice(0, -3) + "y";
  // -ing  (e.g. "depositing" → "deposit")
  if (w.endsWith("ing") && w.length > 5) return w.slice(0, -3);
  // -ed   (e.g. "played" → "play")
  if (w.endsWith("ed") && w.length > 4) return w.slice(0, -2);
  // -es only after sibilants (s, sh, ch, x, z) — e.g. "boxes" → "box", "buses" → "bus"
  if (w.endsWith("es") && w.length > 4) {
    const before = w.slice(-3, -2);
    if (["s", "h", "x", "z"].includes(before)) return w.slice(0, -2);
  }
  // -s   (simple plural: "games" → "game", "friends" → "friend")
  // But NOT for words ending in "ss", "us", "is" (e.g. "bus", "this", "loss")
  if (w.endsWith("s") && w.length > 3) {
    const before = w.slice(-2, -1);
    if (!["s", "u", "i"].includes(before)) return w.slice(0, -1);
  }
  return w;
}

/** Tokenise into stemmed non-stopword tokens. */
export function tokenise(input: string): string[] {
  const norm = normaliseText(input);
  return norm
    .split(" ")
    .filter((t) => t.length > 1 && !STOP_WORDS.has(t))
    .map(stem);
}

/** Levenshtein distance, capped at maxDistance for performance. */
export function editDistance(a: string, b: string, maxDistance = 2): number {
  if (a === b) return 0;
  const la = a.length;
  const lb = b.length;
  if (Math.abs(la - lb) > maxDistance) return maxDistance + 1;
  if (la === 0) return lb;
  if (lb === 0) return la;
  const dp: number[] = new Array(lb + 1);
  for (let j = 0; j <= lb; j++) dp[j] = j;
  for (let i = 1; i <= la; i++) {
    let prev = dp[0];
    dp[0] = i;
    for (let j = 1; j <= lb; j++) {
      const tmp = dp[j];
      dp[j] = Math.min(
        dp[j] + 1, // deletion
        dp[j - 1] + 1, // insertion
        prev + (a[i - 1] === b[j - 1] ? 0 : 1), // substitution
      );
      prev = tmp;
    }
  }
  return Math.min(dp[lb], maxDistance + 1);
}

/** Match a single keyword term against the message tokens. Returns hit weight 0..1. */
export function matchKeyword(
  messageTokens: string[],
  normalisedMessage: string,
  term: string,
  matchType: "broad" | "exact" | "phrase",
): { hit: boolean; weight: number } {
  const termNorm = normaliseText(term);
  if (!termNorm) return { hit: false, weight: 0 };

  if (matchType === "phrase") {
    // Substring match on normalised message (handles "play without depositing money"
    // matching "play without depositing")
    if (normalisedMessage.includes(termNorm)) {
      return { hit: true, weight: 1 };
    }
    // Near-phrase match: tokenise term WITH stopword removal (so "no deposit"
    // matches messages that have "deposit" — the "no" is a stopword), then
    // require ALL non-stopword stemmed tokens to appear in message tokens
    // (within edit distance 1). This prevents "real money" from matching a
    // message that only contains "money".
    const termTokens = tokenise(term);
    if (termTokens.length === 0) return { hit: false, weight: 0 };
    let matchedCount = 0;
    let adjacentMatches = 0;
    let lastMatchIdx = -2;
    for (const tt of termTokens) {
      const idx = messageTokens.findIndex(
        (mt) => mt === tt || editDistance(mt, tt, 1) <= 1,
      );
      if (idx !== -1) {
        matchedCount++;
        if (idx === lastMatchIdx + 1) adjacentMatches++;
        lastMatchIdx = idx;
      }
    }
    // Require ALL tokens present (with optional adjacency for full match)
    if (matchedCount === termTokens.length) {
      // Full match — higher weight if tokens are adjacent in message
      const weight = adjacentMatches >= termTokens.length - 1 ? 1 : 0.85;
      return { hit: true, weight };
    }
    // No partial matches for phrase type — too risky for false positives.
    // (The substring check above already handles the "deposit" inside
    // "depositing" case via normalisation.)
    return { hit: false, weight: 0 };
  }

  if (matchType === "exact") {
    // Whole-phrase exact match (normalised)
    if (normalisedMessage === termNorm) return { hit: true, weight: 1 };
    if (normalisedMessage.includes(termNorm)) return { hit: true, weight: 1 };
    return { hit: false, weight: 0 };
  }

  // broad: any stemmed token of the term appears in message tokens (near-match)
  const termTokens = termNorm.split(" ").map(stem).filter(Boolean);
  if (termTokens.length === 0) return { hit: false, weight: 0 };
  let hits = 0;
  for (const tt of termTokens) {
    const found = messageTokens.some(
      (mt) => mt === tt || editDistance(mt, tt, 1) <= 1,
    );
    if (found) hits++;
  }
  if (hits === 0) return { hit: false, weight: 0 };
  return { hit: true, weight: Math.min(1, hits / termTokens.length) };
}

/** Detect risk flags from message text. */
export function detectRiskFlags(message: string): RiskFlag[] {
  const m = normaliseText(message);
  const raw = message.toLowerCase(); // keep dots / slashes for URL patterns
  const flags: RiskFlag[] = [];
  // underage indicators
  if (
    /\b(i am|im|i'm)\s+(1[0-7]|[0-9])\b/.test(m) ||
    /\bunder\s*18\b/.test(m) ||
    /\bunderage\b/.test(m) ||
    /\bminor\b/.test(m) ||
    /\b(13|14|15|16|17)\s*years?\b/.test(m)
  ) {
    flags.push("underage");
  }
  // real-money gambling request
  if (
    /\breal\s*money\b/.test(m) ||
    /\bcash\s*app\b/.test(m) ||
    /\bstake\s*real\b/.test(m) ||
    /\bdeposit\s*(money|cash|usd|usdt|btc|crypto)\b/.test(m) ||
    /\bwithdraw\s*(money|winnings|usd|usdt|btc|crypto)\b/.test(m) ||
    /\bgambling\s*site\b/.test(m) ||
    /\bodds?\s*for\s*real\b/.test(m)
  ) {
    flags.push("real_money");
  }
  // spam / promotional bait — check raw message for URL patterns
  if (
    /discord\.gg\//.test(raw) ||
    /t\.me\//.test(raw) ||
    /\bdm me\b/.test(m) ||
    /\bdm\s*for\s*link\b/.test(m) ||
    /\bcheck\s*my\s*profile\b/.test(m) ||
    /\bpromo\s*code\b/.test(m) ||
    /\bfollow\s*me\b/.test(m) ||
    /\breferral\s*link\b/.test(m)
  ) {
    flags.push("spam");
  }
  return flags;
}

/** Detect special signal boosts that aren't simple keyword matches. */
export function detectSignals(message: string) {
  const m = normaliseText(message);
  return {
    asksRecommendation: /\b(recommend|suggestion|any good|looking for|anyone know|whats a good|what's a good)\b/.test(m),
    mentionsNoDeposit:
      /\bno\s*deposit\b/.test(m) ||
      /\bwithout\s*depositing\b/.test(m) ||
      /\bfree\s*no\s*deposit\b/.test(m) ||
      /\bdeposit\s*free\b/.test(m) ||
      // "don't have to deposit" / "doesn't need to deposit" patterns
      // After normalisation apostrophes become spaces, so "don't" → "don t".
      /\bdon\s*t\s*(have|need)\s*to\s*deposit\b/.test(m) ||
      /\bdoesn\s*t\s*(have|need)\s*to\s*deposit\b/.test(m) ||
      /\bwithout\s*a\s*deposit\b/.test(m) ||
      /\bno\s*need\s*to\s*deposit\b/.test(m),
    mentionsFree:
      /\bfree\s*to\s*play\b/.test(m) ||
      /\bfree\s*game\b/.test(m) ||
      /\bf2p\b/.test(m) ||
      /\bfree\b/.test(m),
    mentionsGame:
      /\bgame\b/.test(m) || /\bapp\b/.test(m) || /\bsite\b/.test(m),
    mentionsSocial:
      /\bsocial\b/.test(m) ||
      /\bfriends?\b/.test(m) ||
      /\bcommunity\b/.test(m),
    promotional:
      /\bcheck\s*out\b/.test(m) ||
      /\bjoin\s*my\b/.test(m) ||
      /\bshill\b/.test(m),
    offTopic:
      /\bporn\b/.test(m) ||
      /\bgore\b/.test(m) ||
      /\bdrug\b/.test(m),
  };
}

/** Determine confidence based on signal clarity & risk flags. */
export function determineConfidence(
  contributions: ScoreContribution[],
  riskFlags: RiskFlag[],
): "low" | "medium" | "high" {
  if (riskFlags.length > 0 && !riskFlags.includes("negative_keyword")) {
    return "high"; // strong signal
  }
  const totalAbs = contributions.reduce(
    (s, c) => s + Math.abs(c.points),
    0,
  );
  if (totalAbs >= 30) return "high";
  if (totalAbs >= 12) return "medium";
  return "low";
}

/** Determine intent from score using thresholds.
 *  Thresholds are LOWER bounds: score >= thresholds.high → high, etc.
 */
export function intentFromScore(
  score: number,
  thresholds: { notRelevant: number; low: number; medium: number; high: number },
  hasRiskFlag: boolean,
): Intent {
  if (hasRiskFlag) return "not_relevant";
  if (score >= thresholds.high) return "high";
  if (score >= thresholds.medium) return "medium";
  if (score >= thresholds.low) return "low";
  return "not_relevant";
}

export interface ScoreResult {
  score: number;
  intent: Intent;
  confidence: "low" | "medium" | "high";
  matchedKeywords: string[];
  contributions: ScoreContribution[];
  riskFlags: RiskFlag[];
}

/** Score a message against the tuning config. Pure function. */
export function scoreMessage(
  message: string,
  config: TuningConfig,
  country?: string,
  postedAt?: string,
): ScoreResult {
  const normalisedMessage = normaliseText(message);
  const messageTokens = tokenise(message);
  const contributions: ScoreContribution[] = [];
  const matchedKeywords: string[] = [];

  // Risk flags override score color — detect first
  const riskFlags = detectRiskFlags(message);
  // Also: negative-keyword risk flag
  for (const nk of config.negativeKeywords) {
    const { hit } = matchKeyword(messageTokens, normalisedMessage, nk.term, nk.matchType);
    if (hit) {
      riskFlags.push("negative_keyword");
      break;
    }
  }

  // Positive keyword boosts
  for (const kw of config.keywords) {
    const { hit, weight } = matchKeyword(
      messageTokens,
      normalisedMessage,
      kw.term,
      kw.matchType,
    );
    if (hit) {
      const points = Math.round(kw.weight * weight);
      contributions.push({
        ruleId: kw.id,
        label: `"${kw.term}" (${kw.matchType})`,
        points,
      });
      matchedKeywords.push(kw.term);
    }
  }

  // Negative keyword penalties
  for (const nk of config.negativeKeywords) {
    const { hit, weight } = matchKeyword(
      messageTokens,
      normalisedMessage,
      nk.term,
      nk.matchType,
    );
    if (hit) {
      const points = Math.round(nk.weight * weight);
      contributions.push({
        ruleId: nk.id,
        label: `Negative: "${nk.term}"`,
        points,
      });
      if (!matchedKeywords.includes(nk.term)) matchedKeywords.push(nk.term);
    }
  }

  // Signal-based boosts
  const signals = detectSignals(message);
  if (signals.asksRecommendation) {
    contributions.push({
      ruleId: "signal_asks_recommendation",
      label: "Asks for a recommendation",
      points: config.scoring.boosts.asksRecommendation,
    });
  }
  if (signals.mentionsNoDeposit) {
    contributions.push({
      ruleId: "signal_no_deposit",
      label: "Mentions no deposit",
      points: config.scoring.boosts.mentionsNoDeposit,
    });
  }
  if (signals.mentionsFree) {
    contributions.push({
      ruleId: "signal_free",
      label: "Mentions free / free-to-play",
      points: config.scoring.boosts.mentionsFree,
    });
  }
  if (signals.mentionsGame) {
    contributions.push({
      ruleId: "signal_game",
      label: "Mentions game / app / site",
      points: config.scoring.boosts.mentionsGame,
    });
  }
  if (signals.mentionsSocial) {
    contributions.push({
      ruleId: "signal_social",
      label: "Mentions social / community",
      points: config.scoring.boosts.mentionsSocial,
    });
  }

  // Country boost / penalty
  if (country) {
    const c = config.countries.find((c) => c.code === country);
    if (c) {
      if (c.priority === "high") {
        contributions.push({
          ruleId: `country_${country}`,
          label: `High-priority country (${country})`,
          points: config.scoring.boosts.highPriorityCountry,
        });
      } else if (c.priority === "low") {
        contributions.push({
          ruleId: `country_${country}`,
          label: `Low-priority country (${country})`,
          points: config.scoring.penalties.lowPriorityCountry,
        });
      }
    }
  }

  // Recent-post boost
  if (postedAt) {
    const ageHours = (Date.now() - new Date(postedAt).getTime()) / 3.6e6;
    if (ageHours < 24) {
      contributions.push({
        ruleId: "recent_post",
        label: "Posted within 24h",
        points: config.scoring.boosts.recentPost,
      });
    }
  }

  // Penalty for off-topic / promotional
  if (signals.offTopic) {
    contributions.push({
      ruleId: "off_topic",
      label: "Off-topic content",
      points: config.scoring.penalties.offTopic,
    });
    riskFlags.push("off_topic");
  }
  if (signals.promotional) {
    contributions.push({
      ruleId: "promotional",
      label: "Promotional bait",
      points: config.scoring.penalties.promotional,
    });
    if (!riskFlags.includes("spam")) riskFlags.push("spam");
  }

  // Sum and clamp
  const raw = contributions.reduce((s, c) => s + c.points, 0);
  const score = Math.max(0, Math.min(100, raw));
  const hasRisk = riskFlags.length > 0;
  const intent = intentFromScore(score, config.thresholds, hasRisk);
  const confidence = determineConfidence(contributions, riskFlags);

  return {
    score,
    intent,
    confidence,
    matchedKeywords,
    contributions,
    riskFlags,
  };
}

/** Convenience: bucket any score into the global default bands. */
export function intentForScore(score: number, hasRiskFlag: boolean): Intent {
  if (hasRiskFlag) return "not_relevant";
  if (score >= INTENT_META.high.min) return "high";
  if (score >= INTENT_META.medium.min) return "medium";
  if (score >= INTENT_META.low.min) return "low";
  return "not_relevant";
}

/** Plain-English confidence explanation. */
export function confidenceExplanation(
  confidence: "low" | "medium" | "high",
  contributions: ScoreContribution[],
): string {
  if (confidence === "high") {
    return `${contributions.length} rules matched with real weight behind them. This one is very likely relevant.`;
  }
  if (confidence === "medium") {
    return `Some rules matched, but not with much weight. Worth reading before you approve.`;
  }
  return `Barely anything matched. Probably not worth a reply.`;
}

/** Draft a reply variant for a given conversation + tone + voice config. */
export function draftReply(
  conversation: Pick<
    Conversation,
    "message" | "platform" | "community" | "country" | "matchedKeywords"
  >,
  tone: "helpful" | "concise" | "conversational",
  voice: TuningConfig["voice"],
): string {
  const platformLabel = conversation.platform;
  const community = conversation.community;
  const isHighEmoji = voice.emoji >= 50;
  const isHighFriendliness = voice.friendliness >= 65;
  const isHighFormality = voice.formality >= 60;
  const isHighCta = voice.ctaStrength >= 65;
  const greeting = isHighFormality
    ? "Hello"
    : isHighFriendliness
      ? "Hey there"
      : "Hi";
  // Disclosure leads rather than trails: people skim the first line, and a
  // brand connection buried in a closing parenthesis reads like a dark pattern.
  const disclosure = "Full disclosure, I work on Join All Bettors.";
  const fpClause = "Free to play, no deposits, 18+.";
  const url = "https://joinallbettors.example";

  if (tone === "concise") {
    return `${greeting}. ${disclosure} It's a free prediction game, which sounds like what you're after. ${fpClause} ${url}`.slice(
      0,
      voice.maxLength,
    );
  }

  if (tone === "conversational") {
    const opener = isHighFriendliness
      ? `${greeting}! Saw your post in ${community}. ${disclosure}`
      : `${greeting}, saw your post in ${community}. ${disclosure}`;
    const body = `We made a free social prediction game: pick outcomes, earn points, climb a leaderboard. No money in it anywhere. ${fpClause}`;
    const cta = isHighCta
      ? `Want the link? ${url}`
      : `Link's here if you fancy a look: ${url}`;
    const emoji = isHighEmoji ? " 🙂" : "";
    return `${opener} ${body} ${cta}${emoji}`.slice(0, voice.maxLength);
  }

  // helpful
  const opener = `${greeting}, thanks for asking in ${community}. ${disclosure}`;
  const body = `It might be what you're after: pick outcomes, earn points, climb a leaderboard, and no real money changes hands. ${fpClause}`;
  const cta = isHighCta
    ? `You can try it here: ${url}`
    : `Link if it's useful: ${url}`;
  const emoji = isHighEmoji ? " 🎯" : "";
  return `${opener} ${body} ${cta}${emoji}`.slice(0, voice.maxLength);
}
