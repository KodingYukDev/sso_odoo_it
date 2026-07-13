FROM node:24-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM node:24-alpine
ENV NODE_ENV=production
WORKDIR /app
RUN addgroup -S accounts && adduser -S accounts -G accounts
COPY --from=dependencies /app/node_modules ./node_modules
COPY --chown=accounts:accounts package.json ./
COPY --chown=accounts:accounts src ./src
USER accounts
EXPOSE 3000
CMD ["node", "src/server.js"]
