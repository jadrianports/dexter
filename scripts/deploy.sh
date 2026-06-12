#!/bin/bash
# scripts/deploy.sh — update Dexter on Oracle (D-13)
#
# PURPOSE:
#   Pull the latest code from git, rebuild only the bot service image, tail
#   the bot logs briefly to confirm a clean start, and ping the dead-man switch
#   to signal a successful deploy.
#
# DEPLOYMENT:
#   Run manually on the Oracle VM host from the repo root:
#       bash /opt/dexter/scripts/deploy.sh
#   Make executable on the host: chmod +x /opt/dexter/scripts/deploy.sh
#
# ENVIRONMENT:
#   HEALTHCHECK_URL — optional. Set in the crontab environment or sourced
#   externally. If present, a success ping is sent to Healthchecks.io after
#   the deploy completes. The ping is non-fatal (|| true) so a network blip
#   does not abort the deploy.
#   Example crontab wiring:
#       HEALTHCHECK_URL=https://hc-ping.com/<your-uuid>
#   Do NOT source .env directly here — that file is inside the Docker context.
#
# SECURITY: no secrets are hardcoded here (T-05-06); all env vars are read
#   from the environment only.
#
# ============================================================================
# WARNING: NEVER run 'docker compose down -v' in production.
#
#   That command DESTROYS all three named Docker volumes:
#     - postgres_data  → complete, unrecoverable database loss
#     - audio_cache    → all cached audio files deleted
#     - logs           → all log files deleted
#
#   Only 'docker compose down' (without -v) is safe. Better yet: use this
#   script — it calls 'docker compose up -d --build bot', which updates the
#   bot image in-place and leaves every volume intact.
# ============================================================================

set -euo pipefail

REPO_DIR="/opt/dexter"
cd "${REPO_DIR}"

echo "[deploy.sh] Verifying clean working tree before deploy..."
if [ -n "$(git status --porcelain)" ]; then
  echo "[deploy.sh] Working tree is dirty — refusing to deploy. Commit or stash local changes first." >&2
  exit 1
fi

echo "[deploy.sh] Pulling latest changes from git (fast-forward only)..."
git fetch origin
git pull --ff-only

echo "[deploy.sh] Rebuilding bot image (--build bot only — Postgres image is pinned and never rebuilt)..."
docker compose up -d --build bot

echo "[deploy.sh] Tailing bot logs for 15 seconds (Ctrl+C to stop early)..."
docker compose logs -f bot --tail=50 &
TAIL_PID=$!
sleep 15
kill "${TAIL_PID}" 2>/dev/null || true

# Ping Healthchecks.io to signal a successful deploy (non-fatal — same idiom as keepalive.sh).
if [ -n "${HEALTHCHECK_URL:-}" ]; then
    echo "[deploy.sh] Pinging healthcheck to signal deploy complete..."
    curl -fsS --max-time 10 "${HEALTHCHECK_URL}" > /dev/null 2>&1 || true
fi

echo ""
echo "[deploy.sh] Deploy complete."
echo ""
echo "============================================================================"
echo "WARNING: NEVER run 'docker compose down -v' in production."
echo "  That wipes the postgres_data, audio_cache, and logs volumes permanently."
echo "  Use 'docker compose up -d --build bot' (this script) for all updates."
echo "============================================================================"
