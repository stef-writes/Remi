# REMI sandbox image — isolated Python execution environment.
#
# This image runs agent-generated code in a throwaway container per
# session.  It intentionally has NO access to the REMI source tree or
# application secrets; it communicates back to the API only via HTTP
# through the REMI_API_URL environment variable injected at container
# start time.
#
# Security posture
# ----------------
# - Non-root user (sandbox) with no sudo
# - Only the standard library + data/analytics packages installed
# - No Docker socket, no host mount, no privileged flag
# - Network egress limited to REMI_API_URL by the Docker network
#   policy defined in docker-compose.yaml
#
# Build
# -----
#   docker build -t remi-sandbox:latest ./sandbox
#
# The API container spawns sessions via DockerSandbox, which starts
# each container with `sleep infinity` and uses `docker exec` for code
# execution.  Network is restricted to the remi_sandbox internal bridge.

FROM python:3.13-slim

# Analytics packages only — NO networking libraries (httpx, requests,
# aiohttp, urllib3).  The only way to reach outside the sandbox is via
# the injected ``remi`` module, which uses stdlib urllib against the
# internal REMI_API_URL.
RUN pip install --no-cache-dir \
        pandas \
        numpy \
        scipy \
        scikit-learn \
        statsmodels

# Non-root execution — agents should not be able to install packages
# or modify the image layer even if they escape the exec() boundary.
RUN useradd --create-home --shell /bin/false --uid 1001 sandbox
USER sandbox

WORKDIR /session

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp

HEALTHCHECK --interval=30s --timeout=5s --retries=2 \
    CMD ["python", "-c", "print('ok')"]

# Entry point is intentionally left unset; DockerSandbox starts
# containers with `sleep infinity` and execs code into them.
