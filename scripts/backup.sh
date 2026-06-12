#!/bin/bash
# scripts/backup.sh — pg_dump to Oracle Object Storage (D-12)
#
# PURPOSE:
#   Dumps the Dexter Postgres database (custom format, compressed) and pushes it to
#   Oracle Object Storage bucket 'dexter-backups' (Always Free 20 GB). Survives Oracle
#   instance reclaim — object storage persists independently of the compute VM (D-12).
#
# DEPLOYMENT:
#   - Run on the Oracle VM host (outside Docker) via crontab.
#   - Recommended crontab entry (every 6 hours):
#       0 */6 * * * /opt/dexter/scripts/backup.sh
#   - Make executable on the host: chmod +x /opt/dexter/scripts/backup.sh
#
# PREREQUISITES:
#   1. oci-cli installed and configured on the host (API key or instance principal).
#      Instance principal is recommended (no key files to manage):
#      https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm
#   2. An Object Storage bucket named 'dexter-backups' exists in your tenancy.
#      Always Free tier provides 20 GB — more than enough for the roast-fuel DB.
#   3. pg_dump (PostgreSQL client tools) installed on the host:
#        sudo apt-get install -y postgresql-client
#
# POSTGRES AUTH:
#   - The Postgres password must NOT be hardcoded in this script (T-04-05).
#   - Options (choose one):
#       a) ~/.pgpass file (recommended): create /root/.pgpass (or ~dexter/.pgpass):
#            localhost:5432:dexter:dexter:YOUR_POSTGRES_PASSWORD
#          then: chmod 600 ~/.pgpass
#       b) Set PGPASSWORD in the crontab environment:
#            PGPASSWORD=your_password
#            0 */6 * * * /opt/dexter/scripts/backup.sh
#   - pg_dump --no-password ensures it fails fast rather than hanging for interactive input.
#
# NOTE: The Postgres container exposes its default port (5432) to localhost on the Oracle VM.
#   pg_dump connects to localhost, not to the container name 'postgres'.
#   Ensure the docker-compose.yml (or a separate ports: directive) exposes 5432 to the host
#   if pg_dump is run from the host. Alternatively, run pg_dump inside the container:
#     docker compose exec postgres pg_dump -U dexter --format=custom dexter | oci os object put ...

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BUCKET="dexter-backups"
OBJECT_NAME="dexter_${TIMESTAMP}.dump"

echo "[backup.sh] Starting Postgres backup: ${OBJECT_NAME}"

pg_dump \
  --host=localhost \
  --username=dexter \
  --no-password \
  --format=custom \
  "dexter" \
| oci os object put \
    --bucket-name "${BUCKET}" \
    --name "${OBJECT_NAME}" \
    --file - \
    --force

echo "[backup.sh] Backup complete: oci://${BUCKET}/${OBJECT_NAME}"
