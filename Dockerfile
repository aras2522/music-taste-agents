# Music Taste Agents — production image
FROM python:3.12-slim

WORKDIR /app

# System deps for lxml / curl-cffi style packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for reproducible dependency installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependency metadata first (better layer caching)
COPY pyproject.toml README.md ./
COPY app ./app

RUN uv pip install --system .

ENV PYTHONUNBUFFERED=1 \
    PORT=8787 \
    LLM_PROVIDER=gemini

EXPOSE 8787

# Pass secrets at runtime: -e GEMINI_API_KEY=...  (never bake keys into the image)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
