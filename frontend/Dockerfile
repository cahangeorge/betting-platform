FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS builder

WORKDIR /app

ARG PUBLIC_API_URL=""
ENV PUBLIC_API_URL=$PUBLIC_API_URL

RUN npm install -g pnpm@10.34.5

COPY package.json pnpm-lock.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build && pnpm prune --prod

FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS runner

WORKDIR /app

RUN addgroup -S -g 1001 nodeuser \
    && adduser -S -u 1001 -G nodeuser nodeuser

COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./
COPY --from=builder /app/pnpm-lock.yaml ./
COPY --from=builder /app/node_modules ./node_modules

RUN chown -R nodeuser:nodeuser /app

USER nodeuser

EXPOSE 3000

ENV NODE_ENV=production

CMD ["node", "build/index.js"]
