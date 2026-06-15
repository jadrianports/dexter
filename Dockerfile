# Dexter Discord bot image — multi-arch (amd64 on Koyeb/CI, arm64 on dev machines).
# Koyeb builds this Dockerfile directly from git (K-11); docker-compose.yml is local-dev only (K-12).
# Secrets are injected at runtime via env vars — never bake token/key literals into image layers (T-04-05).
FROM python:3.11-slim-bookworm

# Install system deps: ffmpeg (opus audio processing), curl (available in-container if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
