# Signal — Social Intent Radar

> An AI social-listening & reply-approval workspace. Find people publicly
> asking for a product like yours, score how relevant each conversation is,
> and approve or reject an AI-drafted reply before any human posts it.
> **Every reply is human-approved — the app NEVER posts autonomously.**

Demo tenant: **"Join All Bettors"**, a FREE-TO-PLAY social prediction game
(no real money, no deposits, 18+).

---

## Quick start

```bash
bun install            # or: npm install
bun run dev            # http://localhost:3000
bun run lint           # ESLint
bun test src/lib/__tests__/scoring.test.ts   # unit tests for the scoring engine
```

First-run users see a 4-step onboarding wizard (pick platforms → pick
countries → seed keywords → set voice). Skip anytime — re-runnable from the
Safety view.

---

## Tech stack

| Concern | Choice |
|---------|--------|
| Framework | Next.js 16 (App Router) + TypeScript (strict) |
| Styling | Tailwind CSS 4 + shadcn/ui + Radix primitives |
| Motion | Framer Motion (150–200ms, ease-out) |
| State | Zustand (client) + Zod (schemas) |
| Charts | Recharts |
| Data grids | TanStack Table |
| Command palette | cmdk |
| Fonts | Inter (UI), JetBrains Mono (numerals & IDs) |

All data is mocked through `/lib/mockApi.ts` — typed promises with 300–700ms
simulated latency. User config + decisions persist to `localStorage` under
the key `signal.v1` and hydrate on mount to avoid SSR mismatch.

---

## Design system — "Signal"

Calm, warm, editorial analyst tool. Soft depth, lots of whitespace, one
accent per screen.

### Color tokens (CSS variables in `src/app/globals.css`)

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--canvas` | `#FAF9F6` | `#16181A` | page background (warm off-white / charcoal, NOT pure black) |
| `--surface` | `#FFFFFF` | `#1E2124` | cards |
| `--surface-sunk` | `#F4F2ED` | `#262A2E` | inputs, table stripes |
| `--border` | `#E6E2DA` | `#32373C` | hairline borders |
| `--text` | `#1C1B19` | `#F2F0EC` | body text |
| `--text-muted` | `#6B6862` | `#9AA0A6` | secondary text |
| `--primary` | `#0F766E` | `#2DD4BF` | deep teal — actions, links, active nav |
| `--primary-soft` | `#E6F2F0` | `#1B2D2B` | teal tint backgrounds |
| `--success` | `#15803D` | `#4ADE80` | approved, OK |
| `--warning` | `#B45309` | `#FBBF24` | medium intent, awaiting review |
| `--risk` | `#B4405A` | `#F4728E` | muted rose — NEVER pure red |
| `--info` | `#1D4ED8` | `#60A5FA` | charts, links |

### Type scale

11 / 12 / 14 / 16 / 20 / 28 / 40 / 56px. Sentence case for ALL labels.
Micro-labels are 12px, `--text-muted`, medium weight, `letter-spacing: 0.01em`.
Score numerals: JetBrains Mono, `tabular-nums`, `tracking: -0.02em`.

### Shape & depth

- Radius: 8px inputs/badges · 12px cards · 16px modals · 999px pills
- Shadows: `shadow-sm-signal`, `shadow-md-signal`, `shadow-lg-signal`
- Spacing on an 8px grid. Card padding 20–24px. Max content width 1440px.

### Intent color mapping (used everywhere, consistently)

| Band | Score range | Style |
|------|-------------|-------|
| High | 80–100 | teal solid pill |
| Medium | 60–79 | amber outline pill |
| Low | 40–59 | grey outline pill |
| Not relevant | 0–39 | muted grey text |
| Risk-flagged | (any) | rose pill with shield icon, **always overrides score color** |

### Accessibility (hard requirements, all met)

- WCAG 2.1 AA contrast on all text. Minimum body size 14px.
- Full keyboard operability; visible 2px `--primary` focus ring on every control.
- All icon-only buttons have `aria-label`.
- Live regions announce score updates.
- `prefers-reduced-motion` disables all transforms and auto-animations.
- Never encodes meaning in color alone — always paired with an icon or label.

---

## Information architecture

Persistent left sidebar (collapsible to 64px icon rail), top bar with global
search, ⌘K command palette, theme toggle, scan status chip and "Run scan".

1. **Inbox** (`G I`) — the triage surface
2. **Triage** (`G T`) — full-screen focused card stack
3. **Insights** (`G N`) — analytics
4. **Playground** (`G P`) — test a single message
5. **Tuning** (`G U`) — the config layer
6. **Safety** (`G S`) — compliance & guardrails
7. **Activity** (`G A`) — audit log

Mobile (<768px): sidebar becomes a bottom tab bar; Inbox becomes a single
stacked list; the inspector opens as a full-screen sheet; triage mode becomes
swipe-based. All KPI cards become a 2×2 grid. Fully usable.
Tablet (768–1024px): two panes, inspector as an overlay drawer.

---

## Folder structure

```
src/
├── app/
│   ├── globals.css              ← Signal design tokens (light + dark)
│   ├── layout.tsx                ← Inter + JetBrains Mono, ThemeProvider, StoreProvider
│   └── page.tsx                  ← single-page AppShell + view dispatch
├── components/
│   ├── ui/                       ← shadcn/ui primitives (button, card, dialog, …)
│   ├── signal/                   ← shared Signal-specific primitives
│   │   └── primitives.tsx        ← IntentPill, RiskPill, ScoreArc,
│   │                               ScoreBreakdownBar, Sparkline, DeltaChip,
│   │                               PlatformBadge, CountryFlag, EmptyState, Skeleton
│   ├── layout/
│   │   ├── app-shell.tsx         ← sidebar + main column
│   │   ├── top-bar.tsx           ← search, scan chip, Run scan, theme toggle
│   │   ├── command-palette.tsx   ← ⌘K palette
│   │   └── mobile-tab-bar.tsx    ← bottom tab bar (<768px)
│   ├── inbox/                    ← 13 files: kpi-strip, filter-rail, conversation-list,
│   │                               conversation-row, inspector + 4 tabs, bulk-action-bar, …
│   ├── triage/                   ← triage-card, hint-bar, progress, empty-celebration
│   ├── tuning/                   ← 11 files: preview-panel, 6 sections, threshold-editor, unsaved-bar
│   ├── playground/               ← input, results, score-countup, why-this-score, compare-to-queue
│   ├── insights/                 ← 7 chart components + view
│   ├── safety/                   ← guardrails-panel, usage-meter, tos-links, blocked-items
│   ├── activity/                 ← filters, table, export-csv
│   └── onboarding/
│       └── onboarding-wizard.tsx ← 4-step first-run wizard
├── lib/
│   ├── types.ts                  ← Zod schemas + TS types for every entity
│   ├── constants.ts              ← platforms, countries, nav, default tuning config
│   ├── scoring.ts                ← the scoring engine (matcher + contributions)
│   ├── seed.ts                   ← 60 realistic conversations + 8 preview samples
│   ├── mockApi.ts                ← typed promises with simulated latency
│   └── __tests__/
│       └── scoring.test.ts       ← 49 unit tests (bun test)
└── stores/
    └── signal-store.ts           ← Zustand store + localStorage persistence
```

Every file is under 300 lines.

---

## The scoring engine (`src/lib/scoring.ts`)

Pure functions. Used by `mockApi.ts` (seed scoring), the Tuning live preview,
and the Playground analyse flow.

### Pipeline

1. **Normalise** — lowercase, strip punctuation (`[^\p{L}\p{N}\s]`), collapse whitespace.
2. **Tokenise** — split on whitespace, remove stopwords, light-stem each token.
3. **Stem** — strips `-ies→-y`, `-ing`, `-ed`, `-es` (after sibilants only), `-s` (simple plural).
4. **Match** — for each configured keyword:
   - **phrase**: substring match on normalised message (handles "play without depositing money" matching "play without depositing"). Otherwise, require ALL non-stopword stemmed tokens of the term to appear in the message tokens (within edit distance 1).
   - **exact**: whole-phrase match.
   - **broad**: any stemmed token of the term appears (near-match).
5. **Signals** — regex-based boosts: "Asks for a recommendation", "Mentions no deposit", "Mentions free", "Mentions game", "Mentions social".
6. **Risk detection** — `underage`, `real_money`, `spam`. Negative-keyword matches push `negative_keyword`. Off-topic / promotional bait push `off_topic` / `spam`.
7. **Country boost / penalty** — high-priority countries add a boost; low-priority add a penalty.
8. **Recent-post boost** — within 24h.
9. **Sum + clamp** — contributions summed, clamped to 0..100. Risk flags override intent to `not_relevant`.

### Critical correctness properties (verified by tests)

- `"play without depositing money"` matches both `"no deposit"` and `"play without depositing"`.
- `"real money"` does NOT match a message that only contains `"money"`.
- `"deposit required"` does NOT match `"deposit any money"`.
- Underage authors (`"I am 15"`, `"under 18"`, `"16 years old"`) are auto-flagged.
- Real-money requests (`"real money"`, `"deposit cash"`, `"deposit BTC"`) are auto-flagged.
- Spam (`discord.gg/`, `t.me/`, `"DM me"`, `"promo code"`) is auto-flagged.

### Score breakdown

Every score is decomposed into a list of `ScoreContribution` objects:

```ts
{ ruleId: "signal_no_deposit", label: "Mentions no deposit", points: 18 }
{ ruleId: "kw2", label: "\"prediction game\" (phrase)", points: 16 }
{ ruleId: "nk1", label: "Negative: \"real money\"", points: -25 }
```

Rendered as a horizontal stacked bar (`ScoreBreakdownBar`) with a hoverable legend.

---

## Data model

Full TypeScript + Zod schemas in `src/lib/types.ts`. Key entities:

- **`Conversation`** — the core entity (60 seeded). Fields: `id`, `platform`,
  `country`, `community`, `authorPseudonym` (pseudonymised — never real
  handles), `message`, `postedAt`, `language`, `score`, `intent`,
  `confidence`, `matchedKeywords`, `contributions`, `summary`, `riskFlags`,
  `status`, `replyVariants` (3 tones), `selectedVariant`, `editedReply`,
  `history`.
- **`TuningConfig`** — keywords, negativeKeywords, countries, thresholds,
  voice, scoring (boosts + penalties), rateCaps.
- **`ActivityEntry`** — audit log entry (timestamp, actor, action, item,
  before, after).

### Seed dataset

60 conversations spread across all 4 platforms (Discord, Telegram, Facebook,
Reddit) and 8+ countries, scores spanning 0–100, at least 6 risk-flagged
items (2 underage-blocked, 3 real-money-rejected, 3 spam, 2
negative-keyword), varied timestamps across 30 days, and reply variants
that are GENUINELY DIFFERENT per conversation — each variant references the
specific message and community name.

---

## Going live — which `mockApi` functions to replace

Every `mockApi.ts` function returns a typed promise and is swappable 1:1
for a real `fetch()` call. Components consume them via the store or
directly — no component changes required.

```ts
// Before (mock):
export async function listConversations(): Promise<Conversation[]> {
  await delay(latency());
  return readState().conversations;
}

// After (real):
export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch('/api/conversations');
  if (!res.ok) throw new Error('Failed to load conversations');
  return conversationSchema.array().parse(await res.json());
}
```

| Function | Replace with |
|----------|--------------|
| `listConversations()` | `GET /api/conversations` |
| `getConversation(id)` | `GET /api/conversations/:id` |
| `updateConversationStatus(id, status)` | `PATCH /api/conversations/:id` body `{ status }` |
| `updateReply(id, editedReply, selectedVariant)` | `PATCH /api/conversations/:id` body `{ editedReply, selectedVariant }` |
| `bulkUpdateStatus(ids, status)` | `POST /api/conversations/bulk` body `{ ids, status }` |
| `getConfig()` | `GET /api/config` |
| `saveConfig(config)` | `PUT /api/config` |
| `getPreviewSamples()` | keep client-side (calls `generatePreviewSamples`) |
| `analyseMessage(message, meta)` | `POST /api/analyse` body `{ message, ...meta }` (server runs `scoreMessage`) |
| `listActivity()` | `GET /api/activity` |
| `logActivity(...)` | `POST /api/activity` |
| `getKpis(range)` | `GET /api/kpis?range=24h\|7d\|30d` |
| `completeOnboarding()` / `completeTour()` | `POST /api/onboarding/complete` (or keep client-side) |
| `resetAll()` | `DELETE /api/state` |
| `runScan()` | `POST /api/scan` |

The scoring engine (`src/lib/scoring.ts`) is pure and can run on either
client or server. For production, move it server-side and call via the
`analyseMessage` endpoint so the config isn't shipped to the client.

---

## Safety & guardrails (see Safety view)

- ✅ **Human approval required** before any reply is sent. No autonomous posting.
- ✅ **Age safety**: under-18 authors are auto-blocked from reply generation.
- ✅ **Real-money gambling requests** are auto-rejected; product is free-to-play only.
- ✅ **Spam / promotional bait** is auto-rejected.
- ✅ **One reply per person, ever**. No repeat outreach.
- ✅ **Brand connection disclosed** in every reply (locked toggle in Tuning).
- ✅ **Public content only**. Author handles pseudonymised in the UI. No DMs,
  no scraping of private groups, no profile images stored.
- ✅ **Per-platform rate caps** and a **daily approved-reply ceiling** with a
  live usage meter.
- ✅ **Respect each platform's ToS** — linked from the Safety view.

Blocked items are auditable from the Safety view's "Blocked items" tab but
never repliable.

---

## Tests

```bash
bun test src/lib/__tests__/scoring.test.ts
```

49 tests covering: `normaliseText`, `stem`, `tokenise`, `editDistance`,
`matchKeyword` (phrase + broad), `detectRiskFlags`, `scoreMessage` (high-intent,
risky, not-relevant samples), `intentFromScore`, `determineConfidence`.

Critically includes the regression tests for the original Playground bug:
`"real money"` must NOT match a message that only contains `"money"`, and
`"play without depositing money"` MUST match the configured `"no deposit"` /
`"play without depositing"` family.

---

## License

Demo project. Demo tenant "Join All Bettors" is fictional. All conversations
in the seed dataset are synthetic.
