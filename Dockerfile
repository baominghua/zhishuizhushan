FROM node:22.22.0-alpine AS v2-web-builder

WORKDIR /build/apps/web-operations

RUN corepack enable

COPY apps/web-operations/package.json apps/web-operations/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY apps/web-operations/ ./
RUN pnpm run build


# PDAL is not packaged by Debian trixie. Use the official PDAL runtime and pin
# the multi-architecture image digest so production builds remain reproducible.
FROM pdal/pdal:latest@sha256:8e1c89edd76a2d574b7a25675d122aa5eb3a1bfd6a2c50ab124a46769ed05271

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN python --version \
    && pdal --version \
    && pdal --drivers | grep -q writers.copc

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
RUN python -m pip install -r /app/server/requirements.txt

COPY . /app
COPY --from=v2-web-builder /build/dist/web-operations /app/dist/web-operations

EXPOSE 8010

CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${REMOTE_SENSING_PORT:-8010}"]
