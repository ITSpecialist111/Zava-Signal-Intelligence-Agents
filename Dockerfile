# =============================================================================
# Zava Signal Analyst — A2A Protocol Server
# Clean, standalone A2A agent — no Bot Framework SDK needed
# =============================================================================
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ---------------------------------------------------------------------------
# System dependencies for Playwright Chromium
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libwayland-client0 \
    fonts-liberation fonts-noto-color-emoji \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------------------------
COPY pyproject.toml ./
COPY src/__init__.py ./src/__init__.py

RUN pip install --no-cache-dir --pre .  && \
    pip install --no-cache-dir playwright && \
    playwright install chromium && \
    playwright install-deps chromium

# ---------------------------------------------------------------------------
# SDK compatibility patches (ChatAgent ↔ Agent, ai_function ↔ tool)
# ---------------------------------------------------------------------------
COPY scripts/ ./scripts/
RUN python scripts/patch_sdk.py

# ---------------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------------
COPY src/ ./src/
COPY main.py ./
COPY config/ ./config/

# Create data directories
RUN mkdir -p data/reports

# Seed signal data (if available)
COPY data/ ./data/

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "main.py"]
