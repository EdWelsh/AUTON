# Human-written reference recipe (w22 probe self-test and labelled fallback).
FROM node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY index.js ./
COPY public ./public
COPY views ./views
CMD ["node", "index.js"]
