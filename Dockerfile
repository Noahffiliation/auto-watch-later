FROM python:3.14.7-slim-bookworm

RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY auto_watch_later.py .

RUN mkdir -p /data && chown -R appuser:appuser /app /data

ENV DATA_DIR=/data
WORKDIR /data

USER appuser

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/auto_watch_later.py"]
