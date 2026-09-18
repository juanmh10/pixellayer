# Syntax: docker/dockerfile:1
FROM python:3.11-slim

LABEL maintainer="PixelLayer Team"
LABEL description="Production container for PixelLayer AI Image MCP Server"

# Install essential system dependencies for OpenCV and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create dedicated non-root application user
RUN useradd -m -u 1000 pixellayer
WORKDIR /app

# Copy dependency specifications and lockfile for deterministic Docker layer caching
COPY pyproject.toml uv.lock* README.md ./
RUN chown -R pixellayer:pixellayer /app

USER pixellayer

# Install production dependencies into virtual environment using frozen lockfile
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source code
COPY --chown=pixellayer:pixellayer src/ ./src/

# Install the project itself in non-editable mode
RUN uv sync --frozen --no-dev

# Ensure runtime directories exist
RUN mkdir -p /app/models_cache /app/logs /app/workspace

# Configure runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PIXELLAYER_MODELS_CACHE=/app/models_cache \
    PIXELLAYER_ALLOWED_WORKSPACES=/app/workspace \
    PIXELLAYER_LOG_DIR=/app/logs \
    PIXELLAYER_HOST=0.0.0.0 \
    PIXELLAYER_PORT=8000 \
    PIXELLAYER_TRANSPORT=sse

EXPOSE 8000

# Health check to ensure service readiness
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# Run FastMCP in SSE transport mode
CMD ["python", "-m", "src.mcp_server", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]
