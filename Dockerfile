FROM python:3.13-slim

WORKDIR /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY auto_watch_later.py .

CMD ["python", "auto_watch_later.py"]
