# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python dependencies definition
COPY requirements.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project sources
COPY server ./server
COPY ai_agents ./ai_agents
COPY storage ./storage

# Expose Flask environment configuration
ENV FLASK_APP=server.app \
    FLASK_RUN_HOST=0.0.0.0 \
    FLASK_RUN_PORT=5000

EXPOSE 5000

# Default command launches the Flask development server
CMD ["flask", "--app", "server.app", "run", "--host", "0.0.0.0", "--port", "5000"]
