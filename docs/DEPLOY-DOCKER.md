# Dexter — Docker + Neon Run Guide

**Status:** The real, current run path (v1.5)
**Environment:** Docker Compose on your PC (or any always-on box you control) + Neon serverless Postgres
**Cost:** $0/mo, no credit card required

---

## 1. Prereqs

- Docker + Docker Compose installed (`docker --version`, `docker compose version`).
- A Neon project (free tier, no credit card) with a **pooled** connection string
  (Neon console → Connection Details → select "Pooled connection" — the host
  contains `-pooler`).

## 2. Setup

1. Copy the template and fill in your values:
   ```
   cp .env.example .env
   ```
2. Edit `.env` and fill the four required secrets:
   - `DISCORD_TOKEN` — Discord Developer Portal → your app → Bot → Reset Token
   - `GEMINI_API_KEY` — https://aistudio.google.com/apikey
   - `GENIUS_TOKEN` — https://genius.com/api-clients → Client Access Token
   - `DATABASE_URL` — the Neon **pooled** connection string, e.g.
     `postgresql://user:pass@ep-<id>-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require`.
     The bot strips the `?sslmode=...&channel_binding=...` query string at startup
     (`config.sanitize_database_url`) — paste the raw Neon string as-is, no manual
     editing needed.
3. Build and start the stack:
   ```
   docker compose up -d --build
   ```

`.env` is git-ignored — **never commit it**. `.env.example` contains placeholders
only; treat any real token the same way.

---

## 3. Verify it's alive

```
curl http://localhost:8000/health
```

Expect HTTP 200 with a small `{"status": "ok", ...}` JSON body. A `503` with a
`degraded` status is still truthful reporting (e.g. a cog failed to load) —
not a crash; check the logs below to see why.

Tail the logs to confirm no repeated `ERROR` lines (`dexter.log` also lands in
the `logs` named volume):
```
docker compose logs -f bot
```

---

## 4. Honest framing

This is an **on-demand run on a residential IP**, not a 24/7 cloud standup.
YouTube blocks datacenter IPs — running on your own PC's residential IP is
what makes `/play` actually work. Start the stack when you want Dexter
online; stop it (`docker compose down`) when you don't. The code is
substrate-agnostic (Dockerfile + `DATABASE_URL`), so nothing here prevents a
real always-on host later.

---

## 5. Single-Discord-token warning

**Never run two bot instances on the same Discord token at the same time.**
Two instances sharing one token triggers a Discord gateway conflict — both
disconnect repeatedly in a loop and neither works. If you need to debug
locally while another copy might still be running elsewhere, stop the other
one first.
