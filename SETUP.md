# Signal — Setup Guide

This gets the platform running on a Windows PC and connected to Telegram and
Discord. It takes about 15 minutes the first time.

> Signal **never posts on its own.** It finds conversations, scores them and
> drafts a reply. A person approves every reply before it is sent.

---

## 1. Install the prerequisites

- **Node.js 20 or newer**: https://nodejs.org
- **Python 3.12 or newer**: https://python.org (tick "Add Python to PATH")

## 2. Start the app

Double-click **`run-dev.bat`** in the project folder.

The first run installs everything, which takes a few minutes. It creates
`backend\.env` from the template and opens two windows:

| What | Address |
|------|---------|
| Dashboard | http://localhost:3000 |
| Backend API | http://127.0.0.1:8000/api |
| API docs | http://127.0.0.1:8000/docs |

To stop everything, double-click **`stop-dev.bat`**.

## 3. Fill in `backend\.env`

Open `backend\.env` in Notepad and fill in these values:

| Key | What to put |
|-----|-------------|
| `SECRET_KEY`, `JWT_SECRET`, `PSEUDONYM_SALT` | A long random string each. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and use a **different** one for each key. Set `PSEUDONYM_SALT` once and never change it. |
| `TELEGRAM_BOT_TOKEN` | The token BotFather gives you (step 5) |
| `DISCORD_BOT_TOKEN`, `DISCORD_APPLICATION_ID` | From the Discord developer portal (step 6) |
| `PUBLIC_BASE_URL` | Leave as is for local testing. On a live server, set it to your public `https://` address, because links in replies use it. |

Save the file, then restart with `stop-dev.bat` and `run-dev.bat`.

> Never share or upload `backend\.env`. It holds your bot tokens.

## 4. Create your login

Open a terminal in the `backend` folder and run:

```
.venv\Scripts\python.exe scripts\create_user.py --email you@example.com --role admin
```

Type a password of at least 10 characters when asked. Then sign in at
http://localhost:3000/login.

## 5. Telegram bot

In Telegram, open **@BotFather** and send these commands:

1. `/newbot`: choose a name and a username (it must end in `bot`).
   Copy the token into `TELEGRAM_BOT_TOKEN`.
2. `/setjoingroups` → choose your bot → **Enable**.
   *Without this, you can find the bot but cannot add it to any group.*
3. `/setprivacy` → choose your bot → **Disable**.
   *Without this, the bot only sees messages that mention it.*

Then add the bot to each group you want to monitor. Some groups need an admin
to approve bots. If you changed the privacy setting after adding the bot,
remove it from the group and add it back.

**Good to know:**
- A bot's **username can never be changed**, only its display name. To get a
  different username, create a new bot with `/newbot` and swap in the new
  token.
- A bot only sees groups it has been added to. Telegram has no global search.

**Test it:** in the `backend` folder, run:

```
.venv\Scripts\python.exe scripts\test_telegram.py
```

It shows the bot's settings and any messages it can see. It never sends
anything.

## 6. Discord bot

1. Go to https://discord.com/developers/applications → **New Application**.
2. Copy the **Application ID** into `DISCORD_APPLICATION_ID`.
3. Open **Bot** → **Reset Token**, then copy the token into `DISCORD_BOT_TOKEN`.
4. On the same page, under **Privileged Gateway Intents**, turn on
   **MESSAGE CONTENT INTENT**. *Without this, every message arrives empty.*
5. Open **OAuth2 → URL Generator**:
   - Under scopes, tick `bot`.
   - Under permissions, tick **View Channels**, **Read Message History** and
     **Send Messages**.
   - Open the generated link and pick a server. You must be an admin of that
     server, or ask an admin to do it.

**Test it:** in the `backend` folder, run:

```
.venv\Scripts\python.exe scripts\test_discord.py
```

It lists the servers and channels the bot can read and scores recent messages.
It never sends anything.

## 7. AI (Ollama, on your own server)

The AI Agent and the AI-written summaries and replies run on **Ollama**, inside
Docker next to Postgres. Nothing is sent to an outside AI service and there are
no usage limits; the trade-off is speed, since the VPS has no GPU.

```
docker exec signal-ollama-1 ollama pull qwen2.5:7b
```

In `backend/.env`:

```
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
```

Optional: `AI_PROVIDER=groq` with `GROQ_API_KEY` switches to Groq's hosted
models (much faster, but the free tier allows 8,000 tokens per minute, which one
agent task can use up). Web search in the agent always uses Groq, so it is only
offered when `GROQ_API_KEY` is set.

## 8. Discovery sources: public posts and comments

These search public content by keyword, so they find people outside your own
communities. Search terms and sources are edited on the **Platforms** page;
only the credentials go in `backend/.env`. All three are read-only: you reply on
the platform yourself and click **Mark posted**.

| Source | What you need | `.env` |
|---|---|---|
| Reddit (posts and comments) | An app at reddit.com/prefs/apps, type "script" | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` |
| YouTube (video comments) | A YouTube Data API v3 key from console.cloud.google.com | `YOUTUBE_API_KEY` |
| Telegram public groups | A dedicated account (spare phone number) and an app at my.telegram.org | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` |

For Telegram, sign the account in once on the server:

```
cd /opt/signal/app/backend
.venv/bin/python scripts/telegram_login.py
```

Type the login code Telegram sends to the account, then copy the printed
`TELEGRAM_SESSION=` line into `.env` and restart: `sudo systemctl restart signal-api`.

## 9. n8n (workflows and alerts)

n8n runs in Docker and is served at `https://signal.joinallbettors.com/n8n/`.
The editor stays locked until its owner account is created (a fresh n8n lets
the first visitor claim it); webhooks under `/n8n/webhook/` are always open.

To get an alert for every strong new lead: in n8n create a workflow that starts
with a **Webhook** node (method POST, path `new-lead`), add an email/Slack/Telegram
node, and activate it. Then set in `.env`:

```
N8N_LEAD_WEBHOOK_URL=http://127.0.0.1:5678/n8n/webhook/new-lead
LEAD_ALERT_MIN_SCORE=70
```

After each scan, Signal posts the new leads at or above that score (platform,
community, score, summary, message and link) with an `X-Signal-Secret` header
carrying `N8N_WEBHOOK_SECRET`.

## 10. Check everything at a glance

The two test scripts above are the quickest check. Each one says whether its bot
is connected and names any setting still to fix, such as group joining or
privacy mode being off. Run them again after any change in BotFather or the
Discord portal.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Can't add the Telegram bot to a group | BotFather → `/setjoingroups` → Enable |
| Telegram bot is in a group but sees nothing | BotFather → `/setprivacy` → Disable, then remove the bot and add it back |
| Telegram test says `getaddrinfo failed` | Your internet provider is blocking Telegram. Use a VPN, or change your DNS to `1.1.1.1` |
| Discord messages score 0 or arrive empty | Turn on MESSAGE CONTENT INTENT (step 6.4) |
| Discord says "forbidden" for a channel | Give the bot's role View Channel and Read Message History there |
| A port is already in use | Run `stop-dev.bat`, then `run-dev.bat` again |
