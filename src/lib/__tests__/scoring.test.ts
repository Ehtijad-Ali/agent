/* ============================================================
   Signal Scoring Engine — unit tests
   Run with: bun test src/lib/__tests__/scoring.test.ts
   ============================================================ */

import { describe, it, expect } from "bun:test";
import {
  normaliseText,
  stem,
  tokenise,
  editDistance,
  matchKeyword,
  detectRiskFlags,
  scoreMessage,
  intentFromScore,
  determineConfidence,
} from "../scoring";
import { DEFAULT_TUNING } from "../constants";
import type { TuningConfig } from "../types";

const config: TuningConfig = JSON.parse(JSON.stringify(DEFAULT_TUNING));

describe("normaliseText", () => {
  it("lowercases", () => {
    expect(normaliseText("Hello WORLD")).toBe("hello world");
  });
  it("strips punctuation", () => {
    expect(normaliseText("hi! how's it going?")).toBe("hi how s it going");
  });
  it("collapses whitespace", () => {
    expect(normaliseText("  a   b  ")).toBe("a b");
  });
  it("preserves unicode letters", () => {
    expect(normaliseText("Olá mundo")).toBe("olá mundo");
  });
});

describe("stem", () => {
  it("stems -ing", () => {
    expect(stem("depositing")).toBe("deposit");
    expect(stem("playing")).toBe("play");
  });
  it("stems -ed", () => {
    expect(stem("played")).toBe("play");
  });
  it("stems -ies to -y", () => {
    expect(stem("countries")).toBe("country");
  });
  it("stems -es", () => {
    expect(stem("boxes")).toBe("box");
  });
  it("stems -s", () => {
    expect(stem("games")).toBe("game");
  });
  it("leaves short words alone", () => {
    expect(stem("a")).toBe("a");
    expect(stem("an")).toBe("an");
    expect(stem("the")).toBe("the");
  });
});

describe("tokenise", () => {
  it("removes stopwords", () => {
    const tokens = tokenise("the quick brown fox jumps over the lazy dog");
    expect(tokens).not.toContain("the");
    expect(tokens).not.toContain("over");
    expect(tokens).toContain("quick");
    expect(tokens).toContain("fox");
  });
  it("stems tokens", () => {
    const tokens = tokenise("playing games with depositing");
    expect(tokens).toContain("play");
    expect(tokens).toContain("game");
    expect(tokens).toContain("deposit");
  });
});

describe("editDistance", () => {
  it("returns 0 for identical strings", () => {
    expect(editDistance("hello", "hello")).toBe(0);
  });
  it("handles single substitution", () => {
    expect(editDistance("cat", "bat")).toBe(1);
  });
  it("handles single insertion", () => {
    expect(editDistance("cat", "cats")).toBe(1);
  });
  it("handles single deletion", () => {
    expect(editDistance("cats", "cat")).toBe(1);
  });
  it("respects maxDistance cap", () => {
    expect(editDistance("abc", "xyz", 1)).toBe(2);
  });
});

describe("matchKeyword — phrase", () => {
  it("exact substring matches with weight 1", () => {
    const result = matchKeyword(
      tokenise("looking for a free prediction game"),
      normaliseText("looking for a free prediction game"),
      "prediction game",
      "phrase",
    );
    expect(result.hit).toBe(true);
    expect(result.weight).toBe(1);
  });

  it("matches 'no deposit' against 'don't have to deposit any money' (stemmed)", () => {
    const msg = "Anyone know a good free prediction game I can play with friends? Looking for something where I don't have to deposit any money, just pure fun.";
    const result = matchKeyword(
      tokenise(msg),
      normaliseText(msg),
      "no deposit",
      "phrase",
    );
    expect(result.hit).toBe(true);
  });

  it("CRITICAL: does NOT match 'real money' against a message that only contains 'money'", () => {
    const msg = "Anyone know a good free prediction game I can play with friends? Looking for something where I don't have to deposit any money, just pure fun.";
    const result = matchKeyword(
      tokenise(msg),
      normaliseText(msg),
      "real money",
      "phrase",
    );
    expect(result.hit).toBe(false);
    expect(result.weight).toBe(0);
  });

  it("CRITICAL: does NOT match 'deposit required' against 'deposit any money'", () => {
    const msg = "I don't have to deposit any money.";
    const result = matchKeyword(
      tokenise(msg),
      normaliseText(msg),
      "deposit required",
      "phrase",
    );
    expect(result.hit).toBe(false);
  });

  it("matches 'real money' when message actually contains 'real money'", () => {
    const msg = "Looking for a real money gambling site, want to deposit crypto.";
    const result = matchKeyword(
      tokenise(msg),
      normaliseText(msg),
      "real money",
      "phrase",
    );
    expect(result.hit).toBe(true);
  });

  it("matches 'play without depositing' inside 'play without depositing money'", () => {
    const msg = "Want to play without depositing money with friends.";
    const result = matchKeyword(
      tokenise(msg),
      normaliseText(msg),
      "play without depositing",
      "phrase",
    );
    expect(result.hit).toBe(true);
    expect(result.weight).toBe(1); // exact substring
  });
});

describe("matchKeyword — broad", () => {
  it("matches any single token of the term", () => {
    const msg = "anyone got a prediction";
    const result = matchKeyword(
      tokenise(msg),
      normaliseText(msg),
      "prediction game",
      "broad",
    );
    expect(result.hit).toBe(true);
    expect(result.weight).toBeGreaterThan(0);
  });
  it("returns false when no tokens match", () => {
    const msg = "what's the weather like";
    const result = matchKeyword(
      tokenise(msg),
      normaliseText(msg),
      "prediction game",
      "broad",
    );
    expect(result.hit).toBe(false);
  });
});

describe("detectRiskFlags", () => {
  it("detects underage when author says 'I am 15'", () => {
    expect(detectRiskFlags("I am 15 and looking for a game")).toContain("underage");
  });
  it("detects underage for 'under 18'", () => {
    expect(detectRiskFlags("I'm under 18")).toContain("underage");
  });
  it("detects real-money gambling requests", () => {
    expect(detectRiskFlags("Looking for a real money gambling site")).toContain("real_money");
  });
  it("detects crypto deposit requests as real-money", () => {
    expect(detectRiskFlags("Want to deposit BTC and cash out winnings")).toContain("real_money");
  });
  it("detects spam with discord.gg links", () => {
    expect(detectRiskFlags("Join my Discord: discord.gg/spamlink")).toContain("spam");
  });
  it("detects spam with 'DM me'", () => {
    expect(detectRiskFlags("DM me for the link!")).toContain("spam");
  });
  it("returns empty for a clean recommendation request", () => {
    expect(detectRiskFlags("Anyone know a good free game to play with friends?")).toEqual([]);
  });
});

describe("scoreMessage — high-intent sample", () => {
  const msg =
    "Anyone know a good free prediction game I can play with friends? Looking for something where I don't have to deposit any money, just pure fun.";

  it("scores high intent (>= 80) without false-positive risk flags", () => {
    const result = scoreMessage(msg, config, "US", new Date().toISOString());
    expect(result.score).toBeGreaterThanOrEqual(80);
    expect(result.intent).toBe("high");
    expect(result.riskFlags).not.toContain("negative_keyword");
    expect(result.riskFlags).not.toContain("real_money");
    expect(result.riskFlags).not.toContain("underage");
    expect(result.riskFlags).not.toContain("spam");
  });

  it("matches 'no deposit' as a keyword", () => {
    const result = scoreMessage(msg, config, "US", new Date().toISOString());
    expect(result.matchedKeywords).toContain("no deposit");
  });

  it("includes 'Asks for a recommendation' boost", () => {
    const result = scoreMessage(msg, config, "US", new Date().toISOString());
    expect(
      result.contributions.some((c) => c.label === "Asks for a recommendation"),
    ).toBe(true);
  });

  it("includes 'Mentions no deposit' boost", () => {
    const result = scoreMessage(msg, config, "US", new Date().toISOString());
    expect(
      result.contributions.some((c) => c.label === "Mentions no deposit"),
    ).toBe(true);
  });
});

describe("scoreMessage — risky samples", () => {
  it("auto-blocks underage authors", () => {
    const msg = "im 15 and looking for a free prediction game";
    const result = scoreMessage(msg, config, "US", new Date().toISOString());
    expect(result.riskFlags).toContain("underage");
  });

  it("flags real-money requests", () => {
    const msg = "Looking for a real money prediction site, want to deposit cash.";
    const result = scoreMessage(msg, config, "US", new Date().toISOString());
    expect(result.riskFlags).toContain("real_money");
  });

  it("flags spam with promo links", () => {
    const msg = "Free game here!! discord.gg/spamlink — DM me for promo code!";
    const result = scoreMessage(msg, config, "US", new Date().toISOString());
    expect(result.riskFlags).toContain("spam");
  });
});

describe("scoreMessage — not-relevant sample", () => {
  it("scores low and flags not_relevant for off-topic messages", () => {
    const msg = "Anyone got a recommendation for a good single-player RPG on Steam?";
    const result = scoreMessage(msg, config, "US", new Date().toISOString());
    expect(result.score).toBeLessThan(40);
    expect(result.intent).toBe("not_relevant");
  });
});

describe("intentFromScore", () => {
  // Thresholds are now LOWER bounds: high=80, medium=60, low=40, notRelevant=0
  const thresholds = { notRelevant: 0, low: 40, medium: 60, high: 80 };
  it("returns 'high' for scores >= 80", () => {
    expect(intentFromScore(85, thresholds, false)).toBe("high");
  });
  it("returns 'medium' for scores 60-79", () => {
    expect(intentFromScore(70, thresholds, false)).toBe("medium");
  });
  it("returns 'low' for scores 40-59", () => {
    expect(intentFromScore(50, thresholds, false)).toBe("low");
  });
  it("returns 'not_relevant' for scores < 40", () => {
    expect(intentFromScore(20, thresholds, false)).toBe("not_relevant");
  });
  it("overrides to 'not_relevant' when risk flag is present", () => {
    expect(intentFromScore(95, thresholds, true)).toBe("not_relevant");
  });
});

describe("determineConfidence", () => {
  it("returns 'high' when risk flags present (excluding negative_keyword)", () => {
    expect(determineConfidence([{ ruleId: "x", label: "x", points: 5 }], ["underage"])).toBe("high");
  });
  it("returns 'high' when total contribution weight is >= 30", () => {
    expect(
      determineConfidence(
        [
          { ruleId: "a", label: "a", points: 14 },
          { ruleId: "b", label: "b", points: 18 },
        ],
        [],
      ),
    ).toBe("high");
  });
  it("returns 'medium' when total contribution weight is 12-29", () => {
    expect(
      determineConfidence([{ ruleId: "a", label: "a", points: 14 }], []),
    ).toBe("medium");
  });
  it("returns 'low' when total contribution weight is < 12", () => {
    expect(
      determineConfidence([{ ruleId: "a", label: "a", points: 4 }], []),
    ).toBe("low");
  });
});
