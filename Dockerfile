FROM node:22.22.0-alpine AS v2-web-builder

WORKDIR /build/apps/web-operations

RUN corepack enable

COPY apps/web-operations/package.json apps/web-operations/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY apps/web-operations/ ./
RUN pnpm run build


FROM python:3.12.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        gdal-bin \
        libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install -r /app/server/requirements.txt

COPY . /app
COPY --from=v2-web-builder /build/dist/web-operations /app/dist/web-operations

EXPOSE 8010

CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${REMOTE_SENSING_PORT:-8010}"]
