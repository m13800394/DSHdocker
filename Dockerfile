FROM node:24-bookworm-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git python3 ripgrep \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/harness
COPY runtime/package.json runtime/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
    && node node_modules/@deepseek-ai/dsh-subprocess-local/scripts/ensure-spawn-helper.mjs \
    && node -e "require('node-addon-require-builtin').getBindingInfo(); require('node-pty'); require('koffi')" \
    && npm cache clean --force \
    && dpkg-query -W > /opt/harness/os-packages.txt
COPY container/ ./container/
COPY upstream.json VERSION ./
RUN mkdir -p /state/home /state/harness /state/cache /workspace \
    && chown -R node:node /state /workspace

ENV NODE_ENV=production \
    HOME=/state/home \
    DSH_HOME=/state/harness \
    XDG_CACHE_HOME=/state/cache \
    PATH=/opt/harness/node_modules/.bin:$PATH
USER node
WORKDIR /workspace
EXPOSE 3080
HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=6 \
    CMD ["node", "/opt/harness/container/healthcheck.mjs"]
ENTRYPOINT ["node", "/opt/harness/container/start.mjs"]

ARG RELEASE_ID=development
ARG SOURCE_SHA256=unknown
LABEL org.opencontainers.image.title="DeepSeek Harness agent runtime" \
      org.opencontainers.image.version=$RELEASE_ID \
      io.mri-harness.source-sha256=$SOURCE_SHA256 \
      io.mri-harness.upstream-version="0.2.1-rc.3"
