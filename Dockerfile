# Cinemath worker image (Cloud Run Service + optional Jobs override).
# Default CMD serves HTTP for SaaS CINEMATH_WORKER_URL (POST /v1/generate).

FROM python:3.12-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    dvisvgm \
    ffmpeg \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    texlive-latex-extra \
    texlive-fonts-extra \
    texlive-latex-recommended \
    texlive-science \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Optional TTS layer (Kokoro/Piper): see Dockerfile.narration — does not change this image.
# Default: Cloud Run Service HTTP (`cinemath-worker`). For one-shot Jobs, override CMD to `cinemath-worker-job`.
CMD ["cinemath-worker"]
