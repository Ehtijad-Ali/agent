# Frontend → Backend contract mapping

Required by spec §45. This maps every API-like operation the existing frontend
performs onto a REST endpoint, and records where the frontend's current shape
conflicts with the backend spec.

Source of truth inspected:

| File | What it defines |
|---|---|
| `src/lib/types.ts` | Zod schemas for every wire type. The canonical contract. |
| `src/lib/mockApi.ts` | 18 mock operations |
| `src/stores/signal-store.ts` | Zustand store — **holds the real data path** |
| `src/lib/scoring.ts` | Deterministic scoring engine to be ported to Python |
| `src/lib/constants.ts` | `DEFAULT_TUNING` seed configuration |

---

## 1. Finding that changes the plan: mockApi is mostly not wired up

Spec §36 says "the frontend currently uses a mock API, replace mock API calls
with real fetch calls." That is not what the code does.

`mockApi.ts` exports 18 functions. Only **one** is imported by any component:

```
src/components/views/playground-view.tsx → analyseMessage()
```

Everything else — the Inbox, Triage, Insights, Activity and Tuning screens —
reads from the Zustand store, which calls the seed generator **synchronously at
module scope**:

```ts
// src/stores/signal-store.ts:98-100
const initialConfig: TuningConfig = JSON.parse(JSON.stringify(DEFAULT_TUNING));
const initialConversations = generateSeedConversations(initialConfig);
const initialPreviewSamples = generatePreviewSamples(initialConfig);
```

So the integration surface is **the store, not mockApi**. Replacing mockApi
function bodies with `fetch()` would change almost nothing on screen.

### Consequences

**a. Three store actions are synchronous and must become async.**

`setDraftConfig`, `commitConfig` and `discardConfig` each call
`generatePreviewSamples(cfg)` inline. That runs on every slider drag and every
keystroke in Tuning. Spec §21 makes this a network round trip
(`POST /api/tuning/preview`), which cannot be synchronous.

This requires a frontend change, which §36 asks to avoid. It is unavoidable —
flagged rather than done silently. The change is contained to the store action
plus a debounce; **no component API and no layout changes**, so the constraint
is honoured in substance.

**b. Pagination conflicts with client-side aggregation.**

Spec §5 requires pagination and says "do not return thousands of records at
once." But Insights and the KPI strip aggregate over the **whole** conversation
array client-side:

```ts
// src/components/views/insights-view.tsx:49
return conversations.filter((c) => now - +new Date(c.postedAt) <= ms);
```

Filtering, sorting, saved views, score-range and KPI counts are all computed in
`use-inbox-state.ts` and `insights-view.tsx` from `store.conversations`.

If `GET /api/conversations` returns page 1 of 20, every KPI and every chart
silently becomes "stats for the first 20 rows." That is a correctness bug, not a
cosmetic one.

Resolution: serve aggregates from the server (§26 `/api/insights/*` already
requires this) and let the paginated list feed only the list. Insights and the
KPI strip must read from the insights endpoints rather than from
`store.conversations`. This is a real frontend change and is on the critical
path — it is the reason §26 exists.

**c. `getKpis()` in mockApi is dead code today.** The KPI strip does not call
it. It becomes live when wired to `GET /api/insights/overview`.

---

## 2. Operation → endpoint map

`actor` is currently a client-supplied string defaulting to `"you"`. On the
backend it comes from the JWT subject and is never accepted from the client.

| # | Frontend operation | Method + path | Notes |
|---|---|---|---|
| 1 | `listConversations()` | `GET /api/conversations` | Add filters/sort/pagination per §5. Envelope change — see §3. |
| 2 | `getConversation(id)` | `GET /api/conversations/{id}` | 404 instead of `undefined`. |
| 3 | `updateConversationStatus(id, status)` | `POST /api/conversations/{id}/{action}` | Split into the five §18 verbs, not a generic PATCH. |
| 4 | `updateReply(id, editedReply, selectedVariant)` | `POST /api/conversations/{id}/edit` | Returns the updated Conversation. |
| 5 | `bulkUpdateStatus(ids, status)` | `POST /api/conversations/bulk` | Not in §18; required by the existing bulk-action bar. Per-id results so partial failure is visible. |
| 6 | `getConfig()` | `GET /api/tuning` | |
| 7 | `saveConfig(config)` | `PUT /api/tuning` | Writes a `configuration_versions` row (§4). |
| 8 | `getPreviewSamples()` | `GET /api/tuning/samples` | Fixed sample set. |
| 9 | `rescoreSamples(config)` **sync** | `POST /api/tuning/preview` | **Becomes async.** See finding (a). |
| 10 | `analyseMessage(message, meta)` | `POST /api/playground/analyze` | Same engine as ingestion (§22). |
| 11 | `listActivity()` | `GET /api/activity` | Filters + CSV export (§27). |
| 12 | `logActivity(...)` | — | **Removed.** Client must not write audit rows. Server-side only. |
| 13 | `getKpis(range)` | `GET /api/insights/overview` | Currently unused; becomes live. Real deltas replace the `Math.random()` ones. |
| 14 | `completeOnboarding()` | `POST /api/auth/me/onboarding` | Moves to the user record. |
| 15 | `completeTour()` | `POST /api/auth/me/tour` | Moves to the user record. |
| 16 | `getOnboardingState()` | `GET /api/auth/me` | Folded into the user payload. |
| 17 | `resetAll()` | — | Dev-only; drop in production. Not an API. |
| 18 | `runScan()` | `POST /api/scans/run` | Returns `{scanId, status}` (§23), not `{discovered}`. Caller polls `GET /api/scans/{id}`. |

Endpoints in the spec with no current frontend caller — build them, but no
screen consumes them yet: `/api/insights/platforms`, `/api/insights/keywords`,
`/api/insights/countries`, `/api/insights/funnel`, `/api/replies/{id}/send`,
`/api/platforms`, `/api/safety`, `/api/health/*`.

---

## 3. Wire-shape conflicts to resolve

**Envelope.** §32 mandates `{success, error:{code,message}}` for errors. The
frontend expects bare arrays/objects on success. Decision: success responses stay
bare (or `{items, total, page}` for paginated lists), errors use the §32
envelope. Wrapping success payloads too would touch every component.

**camelCase.** Frontend types are camelCase (`sourceUrl`, `authorPseudonym`,
`matchedKeywords`, `riskFlags`, `replyVariants`, `selectedVariant`,
`editedReply`, `postedAt`, `hits7d`, `matchType`, `ctaStrength`, `maxLength`,
`replyLanguage`, `notRelevant`, `perPlatformPerHour`, `dailyApprovedCeiling`).
Python is snake_case. Resolution: Pydantic v2 models use snake_case internally
with `alias_generator=to_camel` and `populate_by_name=True`, serialising camelCase
so **zero frontend types change**.

**`id` is a string.** `conversationSchema.id` is `z.string()`. Use UUIDs
serialised as strings, never integers.

**Dates are ISO strings**, not epoch numbers. `postedAt`, `timestamp`, `at`,
`createdAt`.

**`ActivityEntry.item`** is a plain string and is `"—"` (em dash) for
system-level entries with no resource. Preserve that sentinel or the Activity
table renders an empty cell.

**`selectedVariant` is a zero-based index** into `replyVariants`, not an id.

**`confidence`** is `"low"|"medium"|"high"` — a separate axis from `intent`.

**Enum values are exact snake_case strings** and must not be renamed:
`not_relevant`, `manually_posted`, `real_money`, `negative_keyword`, `off_topic`.

---

## 4. Scoring engine port

`src/lib/scoring.ts` is deterministic and already has 49 passing tests. It is
ported to Python verbatim — same normalisation, same stemmer, same
Levenshtein cap, same contribution labels — so a message scores identically in
both. Port targets:

| TS | Python |
|---|---|
| `normaliseText` | `matching_service.normalise_text` |
| `stem` | `matching_service.stem` |
| `tokenise` | `matching_service.tokenise` |
| `editDistance` | `matching_service.edit_distance` |
| `matchKeyword` | `matching_service.match_keyword` |
| `detectRiskFlags` | `scoring_service.detect_risk_flags` |
| `detectSignals` | `scoring_service.detect_signals` |
| `determineConfidence` | `scoring_service.determine_confidence` |
| `intentFromScore` | `scoring_service.intent_from_score` |
| `scoreMessage` | `scoring_service.score_message` |

Two details that are easy to get wrong and are covered by tests:

1. **Stopword removal makes the §33 critical test pass.** `"no deposit"`
   tokenises to `["deposit"]` because `no` is a stopword; `"without depositing
   money"` tokenises to `["deposit", "money"]` because `without` is a stopword
   and `depositing` stems to `deposit`. The phrase then matches. Removing `no`
   or `without` from `STOP_WORDS` breaks the critical test.

2. **`contributions` labels are user-visible.** The Inspector renders them
   verbatim (`"free game" (phrase)`, `Negative: "real money"`). Label format is
   part of the contract, not an implementation detail.

### Known scoring defect, carried over deliberately

The matcher has no negation handling. A post saying *"no real money, no
crypto"* matches the negative keyword `real money` and is penalised as though
the author were asking for it — the opposite of what they said. This currently
mis-flags 11 of 20 seeded conversations.

Ported as-is so the Python and TS engines agree. Fixing it is a **separate,
deliberate change** to both engines simultaneously, since §13 requires the
frontend to render the exact same explanation. Not silently "improved" during
the port.
