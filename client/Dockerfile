# syntax=docker/dockerfile:1
FROM node:20-alpine AS base

WORKDIR /app

# Install dependencies first for better caching layers
COPY package.json package-lock.json ./
RUN npm install

# Copy application source
COPY . .

# CRA dev server needs to listen on 0.0.0.0 for container access
ENV HOST=0.0.0.0
ENV PORT=3000

EXPOSE 3000

# Start the React development server
CMD ["npm", "start"]
