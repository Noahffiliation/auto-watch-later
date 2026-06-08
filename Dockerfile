FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY auto_watch_later.py .

ENV DATA_DIR=/data
WORKDIR /data

CMD ["python", "/app/auto_watch_later.py"]