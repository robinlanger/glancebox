ARG TARGETARCH
# Pinned to the digest of the multi-arch index (amd64 + arm64); the tag is kept for readability.
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble@sha256:38dd67fc654b56b3cba611e4c8eb71cd33750e1cd29eea2a5dc00b484817a75f AS base

# Home Assistant add-on labels (ha-addon/): the Supervisor checks io.hass.arch against the host.
FROM base AS base-amd64
LABEL io.hass.arch="amd64"
FROM base AS base-arm64
LABEL io.hass.arch="aarch64"

FROM base-${TARGETARCH} AS runtime
ARG VERSION=dev
LABEL io.hass.type="app" io.hass.version="${VERSION}"

# Layout mirrors the repo so glancebox.__version__ finds /app/VERSION (parents[2] of the package).
WORKDIR /app
COPY --chown=pwuser VERSION ./VERSION
COPY --chown=pwuser server ./server
COPY --chown=pwuser pages ./pages

# Editable install keeps the package at /app/server/glancebox. requirements.lock holds only the
# runtime dependencies, every one pinned by hash; the test tools live in the `test` stage below.
RUN pip install --no-cache-dir --break-system-packages --require-hashes \
    -r server/requirements.lock \
 && pip install --no-cache-dir --break-system-packages --no-deps -e server

ENV PYTHONUNBUFFERED=1 \
    TZ=Europe/Berlin \
    GLANCEBOX_PAGES_DIR=/app/pages

# The base image already ships a non-root user (pwuser) and the browsers.
USER pwuser
WORKDIR /app/server

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"

CMD ["python", "-m", "glancebox", "serve"]

# `docker build --target test`: the runtime image plus pytest & co., so `pytest -m browser` can
# run inside it (CI does that). Not part of the default build.
FROM runtime AS test
USER root
RUN pip install --no-cache-dir --break-system-packages --require-hashes \
    -r /app/server/requirements-dev.lock
USER pwuser

# Default target: the runtime image without test tools.
FROM runtime
