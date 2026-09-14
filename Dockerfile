FROM python:3.15.0rc2-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r appuser && \
    useradd -r -g appuser -u 1000 appuser

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-build --locked --no-dev --no-install-project && \
    rm -f /bin/uv /bin/uvx && \
    pip uninstall -y pip setuptools wheel
COPY auto_watch_later.py .

RUN mkdir -p /data && chown -R appuser:appuser /app /data

ENV DATA_DIR=/data
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /data

USER appuser

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/auto_watch_later.py"]
