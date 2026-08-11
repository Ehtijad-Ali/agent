import type {
  Conversation,
  TuningConfig,
  ReplyVariant,
  RiskFlag,
} from "./types";
import { DEFAULT_TUNING } from "./constants";
import { scoreMessage, draftReply } from "./scoring";

/* ============================================================
   Seed generator — 60 realistic conversations across all 4
   platforms and 8+ countries, with varied timestamps over 30
   days, scores spanning 0–98, at least 6 risk-flagged items,
   and genuinely different reply variants per conversation.
   ============================================================ */

type Platform = Conversation["platform"];

interface SeedInput {
  platform: Platform;
  country: string;
  community: string;
  language: string;
  authorPseudonym: string;
  message: string;
  postedAt: string; // ISO
  sourceUrl?: string;
  status?: Conversation["status"];
  forcedRiskFlags?: RiskFlag[];
}

const PSEUDONYMS = [
  "user_8f2a", "user_b41c", "user_7d33", "user_a92e", "user_3f08",
  "user_c65d", "user_1e27", "user_9b4f", "user_5c83", "user_d1a0",
  "user_2f4e", "user_eb37", "user_4a8c", "user_f2d5", "user_7e91",
  "user_b8a3", "user_0c1f", "user_a4d2", "user_3b57", "user_c0e8",
  "user_6f1b", "user_d94a", "user_2c85", "user_e73f", "user_8b14",
  "user_a03d", "user_5e92", "user_f1c6", "user_4d77", "user_b3e0",
  "user_9f25", "user_1a8c", "user_7c64", "user_e0b2", "user_2d59",
  "user_c8f1", "user_4e30", "user_a5b7", "user_0d3c", "user_b968",
  "user_6a14", "user_d270", "user_3f81", "user_f845", "user_1c92",
  "user_8e07", "user_a176", "user_5c40", "user_e29b", "user_b4d3",
  "user_0f5a", "user_d619", "user_2a87", "user_c3f0", "user_7b25",
  "user_f0a8", "user_4c71", "user_a932", "user_3e64", "user_b1f7",
];

const COMMUNITIES: Record<Platform, string[]> = {
  discord: [
    "free-games-community",
    "prediction-lovers",
    "social-gaming-hub",
    "indie-gamers-united",
    "casual-players-lounge",
  ],
  telegram: [
    "freebies-channel",
    "prediction-chat",
    "social-gamers-ru",
    "free-to-play-talk",
    "casual-fun-group",
  ],
  facebook: [
    "Free Games Finders",
    "Social Prediction Players",
    "Casual Gamers UK",
    "Free-to-Play Friends",
    "Pick-Em Leagues",
  ],
  reddit: [
    "r/freegames",
    "r/socialprediction",
    "r/freetoplays",
    "r/gaming_communities",
    "r/predictiongames",
  ],
};

/* 60 hand-crafted messages. Spread across intent bands and risk flags. */
const SEED_MESSAGES: SeedInput[] = [
  // ----- High intent (clear asks, no-deposit, recommendation) -----
  {
    platform: "discord", country: "US", language: "en",
    community: "free-games-community", authorPseudonym: PSEUDONYMS[0],
    message: "ok so my friends and i run a weekly pickem thing and the app we used just shut down. anyone know a good free prediction game? no deposit ideally, we're not trying to gamble, just want bragging rights",
    postedAt: daysAgo(0, 4),
  },
  {
    platform: "reddit", country: "US", language: "en",
    community: "r/socialprediction", authorPseudonym: PSEUDONYMS[1],
    message: "Is there a free to play prediction game for sports where you don't have to deposit anything? Every one I've tried wants card details before it'll even let you look around. I just want to call games against my friends for points. Recommendations welcome.",
    postedAt: daysAgo(0, 9),
  },
  {
    platform: "telegram", country: "GB", language: "en",
    community: "freebies-channel", authorPseudonym: PSEUDONYMS[2],
    message: "any suggestion for a social prediction game? free, no deposit. i just want a leaderboard me and my friends can argue over",
    postedAt: daysAgo(1, 2),
  },
  {
    platform: "facebook", country: "CA", language: "en",
    community: "Free Games Finders", authorPseudonym: PSEUDONYMS[3],
    message: "Recommend a free game for a Discord community please 🙏 We want a prediction/betting style thing but 100% free to play. No deposit, no crypto. Just points and a scoreboard.",
    postedAt: daysAgo(1, 7),
  },
  {
    platform: "discord", country: "AU", language: "en",
    community: "prediction-lovers", authorPseudonym: PSEUDONYMS[4],
    message: "whats a good free prediction game thats actually social? a friend showed me one ages ago where you play without depositing anything and i cannot for the life of me remember what it was called",
    postedAt: daysAgo(2, 3),
  },
  {
    platform: "reddit", country: "US", language: "en",
    community: "r/freegames", authorPseudonym: PSEUDONYMS[5],
    message: "Looking for a free game rec. Social prediction site where you pick outcomes with friends, free to play, no real money involved. Does that exist or am I describing something that doesn't exist",
    postedAt: daysAgo(2, 11),
  },
  {
    platform: "facebook", country: "GB", language: "en",
    community: "Social Prediction Players", authorPseudonym: PSEUDONYMS[6],
    message: "Can anyone recommend a free betting game where you don't have to put money in? After that community leaderboard vibe, no deposit. Not fussed about prizes, I just want the competition.",
    postedAt: daysAgo(3, 1),
  },
  {
    platform: "telegram", country: "DE", language: "en",
    community: "prediction-chat", authorPseudonym: PSEUDONYMS[7],
    message: "anyone know a good social prediction game? free, play without depositing. just want something the group can compete on",
    postedAt: daysAgo(3, 6),
  },
  {
    platform: "discord", country: "CA", language: "en",
    community: "social-gaming-hub", authorPseudonym: PSEUDONYMS[8],
    message: "suggestion needed. free game where you bet fake points on real outcomes. social leaderboard, no deposit, no real money ever. is there a decent one or are they all just casinos with extra steps",
    postedAt: daysAgo(4, 8),
  },
  {
    platform: "reddit", country: "AU", language: "en",
    community: "r/freetoplays", authorPseudonym: PSEUDONYMS[9],
    message: "Recommend me a free to play prediction game. Social one ideally, bet fake points against friends and climb a ladder. No deposit, no crypto, no real money. Been burned by two of these already this year.",
    postedAt: daysAgo(5, 4),
  },
  {
    platform: "facebook", country: "US", language: "en",
    community: "Casual Gamers UK", authorPseudonym: PSEUDONYMS[10],
    message: "Anyone know a free prediction game that actually holds up with a big community? Want to play without depositing money, just having a laugh with friends on a Friday night.",
    postedAt: daysAgo(5, 10),
  },
  {
    platform: "discord", country: "GB", language: "en",
    community: "casual-players-lounge", authorPseudonym: PSEUDONYMS[11],
    message: "looking for a free social prediction game rec. play without depositing, predict outcomes, rank up. anyone got suggestions that arent an ad",
    postedAt: daysAgo(6, 2),
  },

  // ----- Medium intent -----
  {
    platform: "reddit", country: "IN", language: "en",
    community: "r/freegames", authorPseudonym: PSEUDONYMS[12],
    message: "Anyone here play prediction games just for fun? Something social, nothing with serious money in it. Me and my friends want something to argue about during matches.",
    postedAt: daysAgo(6, 7),
  },
  {
    platform: "discord", country: "PH", language: "en",
    community: "prediction-lovers", authorPseudonym: PSEUDONYMS[13],
    message: "whats a fun game to play with friends online? something casual. weve churned through four this month and everyones bored again. recommendations?",
    postedAt: daysAgo(7, 1),
  },
  {
    platform: "telegram", country: "BR", language: "pt",
    community: "social-gamers-ru", authorPseudonym: PSEUDONYMS[14],
    message: "alguem conhece um jogo de previsao gratuito? tipo aposta social sem dinheiro real, so pra jogar com os amigos",
    postedAt: daysAgo(7, 5),
  },
  {
    platform: "facebook", country: "DE", language: "de",
    community: "Free-to-Play Friends", authorPseudonym: PSEUDONYMS[15],
    message: "Kennt jemand ein kostenloses Vorhersagespiel? Würde gern mit Freunden tippen, ohne echtes Geld. Rangliste wäre super.",
    postedAt: daysAgo(8, 3),
  },
  {
    platform: "discord", country: "US", language: "en",
    community: "social-gaming-hub", authorPseudonym: PSEUDONYMS[16],
    message: "whats a good game to play with online friends? prediction or betting style but free. leaderboard is the main thing im after",
    postedAt: daysAgo(8, 9),
  },
  {
    platform: "reddit", country: "FR", language: "fr",
    community: "r/socialprediction", authorPseudonym: PSEUDONYMS[17],
    message: "Cherche un jeu de pronostics gratuit à jouer entre amis, sans argent réel. Quelqu'un a une reco ?",
    postedAt: daysAgo(9, 4),
  },
  {
    platform: "facebook", country: "CA", language: "en",
    community: "Pick-Em Leagues", authorPseudonym: PSEUDONYMS[18],
    message: "Looking for a free prediction app, something social where I can set up a league with friends. Not betting real money. Any suggestions?",
    postedAt: daysAgo(9, 8),
  },
  {
    platform: "telegram", country: "MX", language: "es",
    community: "casual-fun-group", authorPseudonym: PSEUDONYMS[19],
    message: "alguien sabe de un juego de prediccion gratis? tipo apuestas sociales sin dinero, solo por diversion con amigos",
    postedAt: daysAgo(10, 2),
  },
  {
    platform: "discord", country: "GB", language: "en",
    community: "indie-gamers-united", authorPseudonym: PSEUDONYMS[20],
    message: "hey all, after a recommendation. casual game where you predict stuff with a community. free would be ideal. any ideas?",
    postedAt: daysAgo(10, 6),
  },
  {
    platform: "reddit", country: "US", language: "en",
    community: "r/gaming_communities", authorPseudonym: PSEUDONYMS[21],
    message: "Any social prediction games worth recommending? Free to play, no money. Just for fun with my Discord friends.",
    postedAt: daysAgo(11, 3),
  },
  {
    platform: "facebook", country: "US", language: "en",
    community: "Free Games Finders", authorPseudonym: PSEUDONYMS[22],
    message: "Anyone know a game where you make predictions, earn points and climb a leaderboard? Free, social, no deposits. Asking for a friend (genuinely, for once)",
    postedAt: daysAgo(11, 9),
  },
  {
    platform: "discord", country: "CA", language: "en",
    community: "free-games-community", authorPseudonym: PSEUDONYMS[23],
    message: "i want a prediction style game thats free and social. friends and i are trying to start a private league before the season kicks off. anyone got recommendations?",
    postedAt: daysAgo(12, 5),
  },
  {
    platform: "telegram", country: "US", language: "en",
    community: "free-to-play-talk", authorPseudonym: PSEUDONYMS[24],
    message: "anyone got a free prediction game to recommend? play without depositing, group leaderboard, thats it",
    postedAt: daysAgo(13, 1),
  },

  // ----- Low intent (vague, off-target) -----
  {
    platform: "reddit", country: "US", language: "en",
    community: "r/gaming_communities", authorPseudonym: PSEUDONYMS[25],
    message: "What's everyone playing lately? My rotation has gone stale.",
    postedAt: daysAgo(13, 7),
  },
  {
    platform: "discord", country: "GB", language: "en",
    community: "casual-players-lounge", authorPseudonym: PSEUDONYMS[26],
    message: "anyone got server recs for casual gaming chat? just want somewhere quiet to hang out",
    postedAt: daysAgo(14, 2),
  },
  {
    platform: "facebook", country: "AU", language: "en",
    community: "Casual Gamers UK", authorPseudonym: PSEUDONYMS[27],
    message: "What's fun to play online this weekend? Something for four or five of us.",
    postedAt: daysAgo(14, 8),
  },
  {
    platform: "telegram", country: "CA", language: "en",
    community: "casual-fun-group", authorPseudonym: PSEUDONYMS[28],
    message: "anything worth checking out this week?",
    postedAt: daysAgo(15, 3),
  },
  {
    platform: "reddit", country: "IN", language: "en",
    community: "r/freegames", authorPseudonym: PSEUDONYMS[29],
    message: "Has anyone actually played the game that's all over my feed right now, or is it just marketing",
    postedAt: daysAgo(15, 9),
  },
  {
    platform: "discord", country: "PH", language: "en",
    community: "indie-gamers-united", authorPseudonym: PSEUDONYMS[30],
    message: "got any chill recommendations? something to kill an hour on a slow afternoon",
    postedAt: daysAgo(16, 4),
  },
  {
    platform: "facebook", country: "DE", language: "de",
    community: "Free Games Finders", authorPseudonym: PSEUDONYMS[31],
    message: "Hat jemand Tipps für Online-Spiele fürs Wochenende?",
    postedAt: daysAgo(17, 1),
  },

  // ----- Not relevant / off-topic -----
  {
    platform: "reddit", country: "US", language: "en",
    community: "r/freegames", authorPseudonym: PSEUDONYMS[32],
    message: "Recommendation for a single player RPG on Steam? Free preferred but I'll pay if it's actually good.",
    postedAt: daysAgo(17, 6),
  },
  {
    platform: "discord", country: "GB", language: "en",
    community: "casual-players-lounge", authorPseudonym: PSEUDONYMS[33],
    message: "finally hit 80 last night. whats everyone running for the grind",
    postedAt: daysAgo(18, 2),
  },
  {
    platform: "telegram", country: "US", language: "en",
    community: "freebies-channel", authorPseudonym: PSEUDONYMS[34],
    message: "anyone know how to stop my router dropping every twenty minutes, its driving me mad",
    postedAt: daysAgo(18, 8),
  },
  {
    platform: "facebook", country: "CA", language: "en",
    community: "Casual Gamers UK", authorPseudonym: PSEUDONYMS[35],
    message: "Looking for people to join our Minecraft server, DM me for the IP",
    postedAt: daysAgo(19, 3),
  },
  {
    platform: "reddit", country: "AU", language: "en",
    community: "r/gaming_communities", authorPseudonym: PSEUDONYMS[36],
    message: "Recommend me a podcast about game design. Something I can put on during the commute.",
    postedAt: daysAgo(19, 9),
  },
  {
    platform: "discord", country: "US", language: "en",
    community: "social-gaming-hub", authorPseudonym: PSEUDONYMS[37],
    message: "anyone want to trade steam cards, ive got a pile of duplicates",
    postedAt: daysAgo(20, 4),
  },

  // ----- Risk: underage (auto-blocked) -----
  {
    platform: "discord", country: "US", language: "en",
    community: "free-games-community", authorPseudonym: PSEUDONYMS[38],
    message: "im 15 and looking for a free prediction game to play with friends, any recommendations? dont want to deposit anything obviously",
    postedAt: daysAgo(0, 1),
    forcedRiskFlags: ["underage"],
  },
  {
    platform: "reddit", country: "GB", language: "en",
    community: "r/socialprediction", authorPseudonym: PSEUDONYMS[39],
    message: "16 years old here. anyone know a free prediction game i can play without depositing? want something to do with my friends at school",
    postedAt: daysAgo(2, 5),
    forcedRiskFlags: ["underage"],
  },

  // ----- Risk: real_money (auto-rejected) -----
  {
    platform: "telegram", country: "US", language: "en",
    community: "prediction-chat", authorPseudonym: PSEUDONYMS[40],
    message: "Looking for a real money prediction site. Want to deposit cash and bet on games. Anyone got a recommendation for a gambling site that actually pays out?",
    postedAt: daysAgo(1, 6),
    forcedRiskFlags: ["real_money"],
  },
  {
    platform: "reddit", country: "CA", language: "en",
    community: "r/socialprediction", authorPseudonym: PSEUDONYMS[41],
    message: "anyone know a betting site where i can deposit crypto and withdraw winnings? real money, not free points",
    postedAt: daysAgo(4, 2),
    forcedRiskFlags: ["real_money"],
  },
  {
    platform: "discord", country: "AU", language: "en",
    community: "prediction-lovers", authorPseudonym: PSEUDONYMS[42],
    message: "sick of the free stuff. anyone know a real money gambling site? want to deposit usd and actually cash out",
    postedAt: daysAgo(6, 9),
    forcedRiskFlags: ["real_money"],
  },

  // ----- Risk: spam / promotional bait -----
  {
    platform: "discord", country: "US", language: "en",
    community: "free-games-community", authorPseudonym: PSEUDONYMS[43],
    message: "FREE prediction game right here!!! join my discord discord.gg/spamlink 🔥 DM me for promo code, free coins, deposit bonus!!",
    postedAt: daysAgo(3, 4),
    forcedRiskFlags: ["spam"],
  },
  {
    platform: "telegram", country: "BR", language: "pt",
    community: "freebies-channel", authorPseudonym: PSEUDONYMS[44],
    message: "jogo gratuito de previsao aqui!! t.me/meulink 🔥 DM me for the link, promo code, deposit bonus, follow me!",
    postedAt: daysAgo(5, 8),
    forcedRiskFlags: ["spam"],
  },
  {
    platform: "facebook", country: "US", language: "en",
    community: "Free Games Finders", authorPseudonym: PSEUDONYMS[45],
    message: "Check out my new prediction game!! Referral link in my profile, DM me for the link. Deposit bonuses for early signups!!",
    postedAt: daysAgo(7, 9),
    forcedRiskFlags: ["spam"],
  },

  // ----- Negative keyword -----
  {
    platform: "reddit", country: "GB", language: "en",
    community: "r/socialprediction", authorPseudonym: PSEUDONYMS[46],
    message: "Anyone know a decent gambling site? Betting real money on sports, deposit required is fine, crypto friendly preferred.",
    postedAt: daysAgo(8, 7),
  },
  {
    platform: "discord", country: "US", language: "en",
    community: "social-gaming-hub", authorPseudonym: PSEUDONYMS[47],
    message: "looking for a real money gambling site. crypto deposit, fast withdrawal. recommendations?",
    postedAt: daysAgo(10, 5),
  },

  // ----- Edge cases / ambiguous -----
  {
    platform: "facebook", country: "US", language: "en",
    community: "Social Prediction Players", authorPseudonym: PSEUDONYMS[48],
    message: "Anyone actually tried Join All Bettors? Saw an ad for it, can't tell if it's legit or just another gambling site with a friendlier logo.",
    postedAt: daysAgo(11, 6),
  },
  {
    platform: "reddit", country: "CA", language: "en",
    community: "r/predictiongames", authorPseudonym: PSEUDONYMS[49],
    message: "Is Join All Bettors actually free or is there a deposit hiding behind step three? Not signing up until someone confirms.",
    postedAt: daysAgo(12, 3),
  },
  {
    platform: "discord", country: "GB", language: "en",
    community: "social-gaming-hub", authorPseudonym: PSEUDONYMS[50],
    message: "anyone got a free game recommendation? doesnt have to be prediction, anything social works",
    postedAt: daysAgo(13, 5),
  },
  {
    platform: "telegram", country: "US", language: "en",
    community: "free-to-play-talk", authorPseudonym: PSEUDONYMS[51],
    message: "whats the best free prediction game going? asking for me and my friends, no deposit stuff please",
    postedAt: daysAgo(14, 7),
  },
  {
    platform: "facebook", country: "US", language: "en",
    community: "Free Games Finders", authorPseudonym: PSEUDONYMS[52],
    message: "Looking for a free game where I can compete with friends on a leaderboard. Prediction style preferred but I'm open. No deposits.",
    postedAt: daysAgo(16, 1),
  },
  {
    platform: "discord", country: "CA", language: "en",
    community: "prediction-lovers", authorPseudonym: PSEUDONYMS[53],
    message: "What's everyone's pick for the best free social prediction game right now? Looking for a real recommendation, not someone's referral link.",
    postedAt: daysAgo(17, 4),
  },
  {
    platform: "reddit", country: "US", language: "en",
    community: "r/freegames", authorPseudonym: PSEUDONYMS[54],
    message: "Free game recommendation please. Prediction style, social, no deposit, no real money. It's for a Discord game night with about thirty people.",
    postedAt: daysAgo(18, 9),
  },
  {
    platform: "telegram", country: "GB", language: "en",
    community: "prediction-chat", authorPseudonym: PSEUDONYMS[55],
    message: "anyone know a free prediction game? want to play without depositing money, open to suggestions",
    postedAt: daysAgo(20, 6),
  },
  {
    platform: "facebook", country: "AU", language: "en",
    community: "Pick-Em Leagues", authorPseudonym: PSEUDONYMS[56],
    message: "Looking for a free to play prediction game for me and my friends. No deposit, no real money. Any recommendations?",
    postedAt: daysAgo(21, 3),
  },
  {
    platform: "discord", country: "US", language: "en",
    community: "indie-gamers-united", authorPseudonym: PSEUDONYMS[57],
    message: "any good free betting game recommendations? play without depositing money, community vibe, that sort of thing",
    postedAt: daysAgo(22, 8),
  },
  {
    platform: "reddit", country: "IN", language: "en",
    community: "r/predictiongames", authorPseudonym: PSEUDONYMS[58],
    message: "Free social prediction game for a college friend group? Something casual, no real money involved. Recommendations welcome.",
    postedAt: daysAgo(24, 2),
  },
  {
    platform: "telegram", country: "PH", language: "en",
    community: "casual-fun-group", authorPseudonym: PSEUDONYMS[59],
    message: "anyone here play free prediction games with friends? after recommendations, want a social leaderboard, no deposit",
    postedAt: daysAgo(26, 5),
  },
];

function daysAgo(days: number, hoursAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  d.setHours(d.getHours() - hoursAgo);
  return d.toISOString();
}

/** Build a single Conversation from a seed input by running it through the scorer. */
function buildConversation(seed: SeedInput, config: TuningConfig, idx: number): Conversation {
  const result = scoreMessage(seed.message, config, seed.country, seed.postedAt);
  // Merge forced risk flags (e.g. underage / real_money / spam we know are present)
  const riskFlags = Array.from(
    new Set([...result.riskFlags, ...(seed.forcedRiskFlags || [])]),
  );
  const isBlocked =
    riskFlags.includes("underage") ||
    riskFlags.includes("real_money") ||
    riskFlags.includes("spam");
  const status: Conversation["status"] = seed.status ?? (isBlocked ? "blocked" : "new");

  // Per-conversation reply variants — must reference the specific message
  const variants: ReplyVariant[] = [
    {
      tone: "helpful",
      text: draftReply(
        {
          message: seed.message,
          platform: seed.platform,
          community: seed.community,
          country: seed.country,
          matchedKeywords: result.matchedKeywords,
        },
        "helpful",
        config.voice,
      ),
    },
    {
      tone: "concise",
      text: draftReply(
        {
          message: seed.message,
          platform: seed.platform,
          community: seed.community,
          country: seed.country,
          matchedKeywords: result.matchedKeywords,
        },
        "concise",
        config.voice,
      ),
    },
    {
      tone: "conversational",
      text: draftReply(
        {
          message: seed.message,
          platform: seed.platform,
          community: seed.community,
          country: seed.country,
          matchedKeywords: result.matchedKeywords,
        },
        "conversational",
        config.voice,
      ),
    },
  ];

  const id = `conv_${(idx + 1).toString().padStart(3, "0")}`;
  return {
    id,
    platform: seed.platform,
    country: seed.country,
    community: seed.community,
    sourceUrl:
      seed.sourceUrl ??
      `https://${seed.platform}.example/${seed.community}/post/${id}`,
    authorPseudonym: seed.authorPseudonym,
    message: seed.message,
    postedAt: seed.postedAt,
    language: seed.language,
    score: result.score,
    intent: result.intent,
    confidence: result.confidence,
    matchedKeywords: result.matchedKeywords,
    contributions: result.contributions,
    summary: buildSummary(seed.message, result.matchedKeywords, riskFlags),
    riskFlags,
    status,
    replyVariants: variants,
    selectedVariant: 0,
    history: [
      {
        at: seed.postedAt,
        actor: "system",
        action: "Discovered and scored",
      },
    ],
  };
}

function buildSummary(message: string, matched: string[], riskFlags: RiskFlag[]): string {
  const lower = message.toLowerCase();
  if (riskFlags.includes("underage")) {
    return "Author says they are under 18, so no reply can be drafted for this one.";
  }
  if (riskFlags.includes("real_money")) {
    return "Author wants real-money gambling. Rejected: Join All Bettors is free-to-play only.";
  }
  if (riskFlags.includes("spam")) {
    return "Promotional links and referral codes. Rejected as spam.";
  }
  if (matched.length === 0) {
    return "No keywords matched, and the message is not asking for a recommendation.";
  }
  const isAsking = /\b(recommend|suggestion|any good|looking for|anyone know)\b/.test(lower);
  const isNoDeposit = /\b(no\s*deposit|without\s*depositing)\b/.test(lower);
  const pieces: string[] = [];
  if (isAsking) pieces.push("Author is asking for a recommendation");
  if (isNoDeposit) pieces.push("explicitly mentions no deposit");
  if (matched.some((m) => m.includes("free"))) pieces.push("interested in free-to-play");
  if (matched.some((m) => m.includes("social") || m.includes("friend")))
    pieces.push("wants a social/community experience");
  if (pieces.length === 0) {
    pieces.push(`Matched ${matched.length} configured keywords`);
  }
  return pieces.join(", ") + ".";
}

/** Generate the full seed dataset of 60 conversations. */
export function generateSeedConversations(config: TuningConfig): Conversation[] {
  return SEED_MESSAGES.map((seed, idx) => buildConversation(seed, config, idx));
}

/** 8 sample conversations used in the Tuning live-preview panel. */
export function generatePreviewSamples(config: TuningConfig): Conversation[] {
  // pick a representative slice: high, medium, low, not relevant, risk
  const picks = [0, 11, 12, 25, 32, 38, 40, 43];
  return SEED_MESSAGES.filter((_, idx) => picks.includes(idx)).map((seed, idx) =>
    buildConversation(seed, config, idx),
  );
}
