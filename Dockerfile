FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY config.example.yaml ./config.example.yaml

ENV PYTHONUNBUFFERED=1
EXPOSE 8765

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8765"]
