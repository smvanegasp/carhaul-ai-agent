# The voice worker image: docker compose locally, ECS Fargate from stage 4.
# It connects out to LiveKit Cloud (no inbound port); 8081 serves the worker's health check.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first (cached layer), then the package itself.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# Bake the VAD and turn-detector weights into the image so calls don't wait for downloads.
RUN python -m livekit.agents download-files

# Run as a non-root user.
RUN useradd --create-home mia
USER mia
# The CarHauler catalog snapshot (mia/catalog.py); compose mounts a volume here so restarts
# don't spend API calls re-fetching it.
RUN mkdir -p /home/mia/.cache/mia

EXPOSE 8081
CMD ["python", "-m", "mia.main", "start"]
