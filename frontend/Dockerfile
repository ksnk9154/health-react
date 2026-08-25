# ──────────────────────────────────────────────────────────────────────────────
#  Dockerfile — Production build for the React/Vite frontend
#  Serves static files via nginx (SPA-compatible, handles client-side routing)
# ──────────────────────────────────────────────────────────────────────────────
# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN npm install -g pnpm@8 && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# Production stage — serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
