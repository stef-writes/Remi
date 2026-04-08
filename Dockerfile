# REMI API server — production image.
#
# Multi-stage build using uv for fast, reproducible installs.
# The sandbox image (sandbox/Dockerfile) is separate — it runs
# agent-generated code in isolated containers.

# ---------- build stage ----------
FROM python:3.13-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src/ src/

RUN uv pip install --system ".[all-providers,postgres,analytics,sandbox-docker]"

# ---------- runtime stage ----------
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages \
                    /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin/remi /usr/local/bin/remi

WORKDIR /app

COPY src/ src/
COPY data/ data/

RUN useradd --create-home --shell /bin/false remi
USER remi

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["remi", "serve", "--host", "0.0.0.0", "--port", "8000"]
