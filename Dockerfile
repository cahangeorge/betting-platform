FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install uv && uv sync --no-dev

# Copy backend code
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/data ./data

# Build frontend
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g npm@latest

COPY frontend/package.json frontend/package-lock.json frontend/svelte.config.js frontend/vite.config.ts frontend/tsconfig.json ./
COPY frontend/src ./src
RUN npm install --legacy-peer-deps && npm run build

# Copy build output to where backend expects it
RUN mkdir -p /app/frontend && cp -r build /app/frontend/build

# Expose port
EXPOSE 8000

# Run
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
