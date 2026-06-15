# ─────────────────────────────────────────────────────────────────────────────
# Portfolio Optimizer — Frontend Dockerfile
#
# Multi-stage build:
#   base        — Node.js base with dependencies installed
#   development — Vite dev server (hot-reload via volume mount)
#   builder     — Production build (npm run build)
#   production  — Nginx serving static assets
# ─────────────────────────────────────────────────────────────────────────────

# ── Base ──────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS base

WORKDIR /app

# Copy package manifests first for layer caching
COPY package.json package-lock.json* ./

# ── Development ───────────────────────────────────────────────────────────────
FROM base AS development

RUN npm ci

# Source code is mounted as a volume in docker-compose.yml
EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ── Builder ───────────────────────────────────────────────────────────────────
FROM base AS builder

RUN npm ci

COPY . .

# Build args for production API URLs
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_WS_BASE_URL=ws://localhost:8000

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_WS_BASE_URL=$VITE_WS_BASE_URL

RUN npm run build

# ── Production (Nginx) ────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS production

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx config for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
