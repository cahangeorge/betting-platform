FROM node:22-alpine AS builder

WORKDIR /app

ARG PUBLIC_API_URL=http://localhost:8001
ENV PUBLIC_API_URL=$PUBLIC_API_URL

RUN npm install -g pnpm@10

COPY package.json pnpm-lock.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM node:22-alpine AS runner

WORKDIR /app

RUN addgroup -S -g 1001 nodeuser \
    && adduser -S -u 1001 -G nodeuser nodeuser

COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./
COPY --from=builder /app/pnpm-lock.yaml ./

RUN npm install -g pnpm@10 && pnpm install --prod --frozen-lockfile && pnpm store prune

RUN chown -R nodeuser:nodeuser /app

USER nodeuser

EXPOSE 3000

ENV NODE_ENV=production

CMD ["node", "build/index.js"]
