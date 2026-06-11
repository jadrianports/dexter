#!/bin/bash
# scripts/keepalive.sh — dual-duty keep-alive + dead-man switch (D-09, D-13)
#
# PURPOSE:
#   1. Oracle idle-reclaim hedge (D-09): generates outbound network traffic every 5 min,
#      keeping the VM above Oracle's "< 20% network utilisation (95th pct, 7-day)" idle
#      threshold so the instance is not reclaimed.
#   2. Healthchecks.io dead-man switch (D-13): if this script stops running (bot host is
#      down), Healthchecks.io stops receiving pings and fires an alert (Discord/email).
#
# DEPLOYMENT:
#   - Run OUTSIDE Docker, on the Oracle VM host crontab (D-09) — works even while the
#     bot container is briefly stopped or restarting.
#   - Recommended crontab entry (every 5 minutes):
#       */5 * * * * /opt/dexter/scripts/keepalive.sh
#   - Make executable on the host: chmod +x /opt/dexter/scripts/keepalive.sh
#
# ENVIRONMENT:
#   HEALTHCHECK_URL must be set in the crontab environment or sourced from a file.
#   Do NOT source .env directly here — that file is inside the Docker context, not on host.
#   Example crontab with env:
#       HEALTHCHECK_URL=https://hc-ping.com/<your-uuid>
#       */5 * * * * /opt/dexter/scripts/keepalive.sh
#
# SECURITY: no secrets are hardcoded here (T-04-05); HEALTHCHECK_URL is read from env only.

set -uo pipefail

# Ping Healthchecks.io. Failures are non-fatal (|| true) so a transient network blip
# does not cause cron to report an error or stop future runs.
curl -fsS --max-time 10 "${HEALTHCHECK_URL}" > /dev/null 2>&1 || true
