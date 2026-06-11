# Source: hub.docker.com/r/arm64v8/python; Oracle A1 ARM (arm64) target
# Builds the Dexter Discord bot image with ffmpeg (audio) + curl.
# Secrets are injected at runtime via docker-compose env_file (.env) — never bake
# token/password/key literals into image layers (T-04-05).
FROM python:3.11-slim-bookworm

# Install system deps: ffmpeg (opus audio processing), curl (available in-container if needed)
# arm64-native packages in Debian Bookworm — no cross-compile needed on Oracle A1 ARM.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
