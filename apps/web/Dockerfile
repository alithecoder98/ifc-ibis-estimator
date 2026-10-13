FROM node:20-slim AS base
WORKDIR /app
RUN corepack enable

FROM base AS deps
# pnpm-workspace.yaml carries the allowBuilds approval for unrs-resolver's postinstall
# script - without it this install fails non-interactively (ERR_PNPM_IGNORED_BUILDS).
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV DOCKER_BUILD=1
RUN pnpm build

# Lean runtime: only the standalone server output, not the full node_modules tree.
FROM base AS runner
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
