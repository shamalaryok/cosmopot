# syntax=docker/dockerfile:1.4

FROM node:20-alpine AS builder

ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"

RUN corepack enable && apk add --no-cache libc6-compat

WORKDIR /app

COPY frontend/spa/pnpm-lock.yaml ./pnpm-lock.yaml
COPY frontend/spa/package.json ./package.json
RUN pnpm install --frozen-lockfile

COPY frontend/spa ./
RUN pnpm build

FROM nginx:1.25-alpine AS runtime

WORKDIR /usr/share/nginx/html

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist ./

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD wget -qO- http://localhost:8080/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
