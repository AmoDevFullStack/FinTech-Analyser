# syntax=docker/dockerfile:1
#
# Three stages:
#   dev    what docker-compose.yml builds: the Vite dev server with hot reload.
#   build  compiles the production bundle (tsc + vite build).
#   prod   what .github/workflows/cd.yml publishes: static files served by unprivileged
#          Nginx, which also proxies /api/ to the backend (nginx.conf beside this file).

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---------------------------------------------------------------------------------------
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]

# ---------------------------------------------------------------------------------------
FROM deps AS build
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS prod
ARG BUILD_SHA=unknown
LABEL org.opencontainers.image.revision=${BUILD_SHA}
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
