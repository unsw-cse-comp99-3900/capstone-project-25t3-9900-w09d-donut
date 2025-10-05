# syntax=docker/dockerfile:1
FROM node:20-alpine AS base

WORKDIR /app

# Install dependencies first for better caching
COPY package.json ./package.json
RUN npm install

# Copy application source
COPY . .

EXPOSE 5173

# Start Vite dev server accessible from the host machine
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
