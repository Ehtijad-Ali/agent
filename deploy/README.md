# Deploying Signal on a VPS

One `docker compose` stack runs everything: Caddy (HTTPS), the Next.js
frontend, the FastAPI backend, PostgreSQL, Redis, Ollama and n8n. Only ports
80 and 443 are open to the internet.

## 1. Before you start

- A VPS with **8 GB RAM or more** (the 3B model needs ~3 GB, the rest ~2 GB).
  Ubuntu 22.04/24.04 with Docker installed:
  `curl -fsSL https://get.docker.com | sh`
- DNS **A records** pointing at the server's IP:
  - `signal.joinallbettors.com`
  - `n8n.joinallbettors.com`
- If something else already listens on 80/443 (an existing Caddy or nginx),
  stop it first, or Caddy here cannot get certificates.

## 2. Configure

```bash
git clone https://github.com/Ehtijad-Ali/agent.git signal && cd signal
cp backend/.env.example backend/.env      # tokens, JWT secret, salt (see comments)
cp deploy/.env.example deploy/.env        # domains, database passwords, n8n key
```

In `backend/.env` set at least `SECRET_KEY`, `JWT_SECRET` (32+ chars),
`PSEUDONYM_SALT`, the Discord/Telegram tokens, and
`N8N_WEBHOOK_SECRET` = the same value as `SIGNAL_N8N_SECRET` in
`deploy/.env`. Database, Redis, Ollama and n8n addresses are set by
`docker-compose.yml` and need no editing.

> **Moving from an existing install?** Copy the old `PSEUDONYM_SALT` exactly.
> A new salt re-pseudonymises every author and breaks "one reply per person".

## 3. Start

```bash
cd deploy
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:3b
docker compose exec backend python scripts/create_user.py --email you@example.com --role admin
```

Open `https://signal.joinallbettors.com` and sign in.
`https://signal.joinallbettors.com/api/health` should show `database`,
`redis`, `ollama` and `n8n` all healthy.

## 4. Connect n8n

1. Open `https://n8n.joinallbettors.com` and create the owner account.
2. **Workflows → Import from file** → `deploy/n8n/signal-events.workflow.json`.
3. Replace the three placeholder nodes with what you want: a Telegram or
   email alert for new leads, a Google Sheets row per sent reply, a scan
   digest. Then **Activate** the workflow.

Signal posts these events to n8n (header `X-Signal-Secret`):

| Event | When |
|---|---|
| `lead.discovered` | A scan found a new high/medium-intent lead with no risk flags |
| `lead.status_changed` | A reviewer approved, rejected, snoozed… a lead |
| `reply.sent` | An approved reply was posted |
| `scan.completed` | Every scan, with per-platform counts and errors |

n8n can call Signal back (send header `X-Signal-Secret`):

- `POST http://backend:8000/api/automation/scan` starts a scan
- `GET  http://backend:8000/api/automation/leads?minScore=60&hours=24` lists leads

These cannot approve or send anything; that always needs a signed-in person.

## Day to day

```bash
docker compose logs -f backend          # follow the API and scans
docker compose pull && docker compose up -d --build   # update after git pull
docker compose exec postgres pg_dump -U signal signal > backup-$(date +%F).sql
```
