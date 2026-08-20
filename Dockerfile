FROM node:22.22.0-alpine AS v2-web-builder

ARG NPM_REGISTRY=https://registry.npmmirror.com

ENV COREPACK_NPM_REGISTRY=${NPM_REGISTRY} \
    npm_config_registry=${NPM_REGISTRY} \
    NPM_CONFIG_FETCH_RETRIES=8 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=10000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000 \
    NPM_CONFIG_FETCH_TIMEOUT=600000

WORKDIR /build/apps/web-operations

RUN corepack enable

COPY apps/web-operations/package.json apps/web-operations/pnpm-lock.yaml ./
RUN --mount=type=cache,id=smart-bamboo-pnpm-store,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store \
    && pnpm config set registry "${NPM_REGISTRY}" \
    && pnpm install --frozen-lockfile

COPY apps/web-operations/ ./
RUN pnpm run build


# PDAL is not packaged by Debian trixie. Use the official PDAL runtime and pin
# the multi-architecture image digest so production builds remain reproducible.
FROM pdal/pdal:latest@sha256:8e1c89edd76a2d574b7a25675d122aa5eb3a1bfd6a2c50ab124a46769ed05271

ARG SMART_BAMBOO_BUILD_COMMIT=unknown
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

LABEL org.opencontainers.image.title="Smart Bamboo V2" \
      org.opencontainers.image.revision="${SMART_BAMBOO_BUILD_COMMIT}"

# The PDAL image exposes its base Conda interpreter before the dedicated PDAL
# environment. Application packages are installed into the PDAL environment,
# so keep that interpreter first for both build-time and runtime commands.
ENV PATH=/opt/conda/envs/pdal/bin:${PATH}
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN python --version \
    && pdal --version \
    && pdal --drivers | grep -q writers.copc

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
RUN --mount=type=cache,id=smart-bamboo-pip-cache,target=/root/.cache/pip \
    python -m pip install \
      --index-url "${PIP_INDEX_URL}" \
      --retries 8 \
      --timeout 600 \
      -r /app/server/requirements.txt

ENV PIP_NO_CACHE_DIR=1

COPY . /app
COPY --from=v2-web-builder /build/dist/web-operations /app/dist/web-operations

EXPOSE 8010

CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${REMOTE_SENSING_PORT:-8010}"]
