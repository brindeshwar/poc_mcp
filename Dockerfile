# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8001

WORKDIR /app

# Dependencies first so they are cached across source changes.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY scripts ./scripts
COPY streamlit_app.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8001 8501
CMD ["meeting-hub"]
