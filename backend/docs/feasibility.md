# Feasibility: what this platform can and cannot do

Written because four items in the brief cannot be delivered as written — not
for want of effort, but because the platforms concerned have closed the doors
the brief assumes are open, or because doing it would require paid services the
brief explicitly rules out.

Each item below states what was asked, what is actually possible, and what was
built instead. Where something is blocked, the blocker is named and dated so it
can be re-checked rather than taken on trust.

---

## 1. Facebook lead discovery — not possible

**Asked for:** Facebook as a monitoring and lead-discovery source.

**Status:** blocked by Meta, not by us.

- The Groups API was restricted in April 2020. Reading posts from groups you do
  not own has not been generally available since.
- CrowdTangle, the tool researchers used for public-content monitoring, was
  **shut down in August 2024**.
- Its replacement, the **Meta Content Library**, is limited to approved
  academic and non-profit researchers and **explicitly excludes commercial
  use**. Join All Bettors is a commercial product, so it does not qualify.

**What is possible:** posting to a Facebook Page you own, via the Pages API.
That is publishing, not discovery — it finds nobody.

**Built:** the connector interface reports Facebook as `not_implemented` with
this explanation attached, so the UI states the reason rather than showing a
broken integration. Adding Facebook later is implementing one class, if access
ever reopens.

---

## 2. WhatsApp monitoring — not possible within the cost constraint

**Asked for:** WhatsApp integration, with no recurring bills beyond the server.

**Status:** mutually exclusive.

- There is no official API for reading WhatsApp groups you were not invited to,
  and no API at all for monitoring conversations at large. Messages are
  end-to-end encrypted by design.
- The WhatsApp Business Cloud API exists but is for *outbound* business
  messaging, requires pre-approved templates and opt-in from the recipient, and
  **charges per conversation**. That is a recurring bill, which the brief rules
  out.
- Unofficial libraries that drive a logged-in session violate WhatsApp's terms
  and get numbers banned.

**Built:** nothing. Listed here rather than stubbed, so it is not mistaken for
pending work.

---

## 3. Craigslist auto-posting — content yes, submission no

**Asked for:** an agent that opens craigslist.com, picks an unused US city and
a category, fills in title/city/ZIP/description/email, **submits the ad live**,
and logs the content plus the published URL.

**Status:** everything except the submission.

Craigslist actively defends against automated posting:

- Posting requires phone verification per account, and accounts that post
  across many cities are flagged and blocked.
- Datacenter IP ranges — which is what a Contabo VPS is — are blocked for
  posting. Working around that needs **residential proxies**, a paid monthly
  subscription.
- Captchas appear on the posting flow. Solving them programmatically needs a
  **paid captcha-solving service**.
- Automated posting is against Craigslist's terms of use, and they have
  litigated over it (*Craigslist v. 3Taps*, *Craigslist v. Instamotor*).

So automated submission would require two recurring subscriptions the brief
forbids, and would put the business at risk of an IP ban and a terms-of-use
claim. It was not built for those reasons, not because of the engineering.

**Built — brief §2.1 to §2.7 and §2.9:**

- A `content` agent type you create as many of as you like, each with its own
  contact email and permitted categories.
- 48 US cities with real state and central ZIP data.
- **"A city different from any used before" is enforced by a database
  constraint**, not by remembering to check — asking for an ad when every city
  is used returns an explicit error instead of quietly repeating one.
- Personalised title and body per city, which read differently city to city
  rather than being one template with the name swapped, and which carry the
  mandatory disclosure, free-to-play, no-deposit and 18+ wording.
- Every generated ad is stored with a slot for the published URL, and
  `POST /api/agents/outputs/{id}/publish` records where you posted it. That is
  what the brief asked a Google Sheet to do, held in the platform instead — no
  Google account, no extra bill.

**The gap in practice:** a human copies the generated ad, posts it, and pastes
the URL back. Roughly a minute per city. The alternative costs two
subscriptions and risks the account.

---

## 4. "How many users followed and replied" — partly possible

**Asked for:** analytics on how many users followed the agents, replied to
them, and clicked the tracking links.

**Status:** clicks yes, replies possible, follows no.

- **Clicks: built.** Every outbound reply carries a short link unique to that
  conversation. `/api/insights/engagement` reports replies sent, clicks, unique
  clicks and click-through rate, per platform.
  One subtlety worth knowing: Discord and Telegram both fetch a link the moment
  it is posted, to build a preview. Counting those would show a 100%
  click-through rate on messages nobody opened, so they are detected and
  reported separately as `botHits` rather than silently dropped.
- **Replies received: possible, not yet built.** It needs the connector to
  re-read the thread and match replies against the message id we stored. The
  id is already recorded, so the data is there.
- **Follows: not available.** Neither Discord nor Telegram exposes "who
  followed this bot" for a bot in a server or group. There is no API for it.
  Discord has no follow concept for bots at all.

---

## Rate limits are a design choice, not a defect

Worth stating plainly, because it shapes what the analytics will ever show.

The safety rules cap outreach at **one reply per person, ever**, 5 per platform
per hour, and 30 per day. Those are enforced server-side and cannot be switched
off through the API. They exist to keep the accounts alive — platforms ban bots
that message the same people repeatedly — but they mean engagement volume will
be in the tens per day, not the thousands. Any projection built on higher
numbers is projecting a banned account.
