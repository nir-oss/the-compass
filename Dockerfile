FROM python:3.11-slim

# System deps for Chromium
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium browser + all system dependencies in one step
RUN playwright install --with-deps chromium

COPY . .

RUN mkdir -p /app/output

EXPOSE 10000

CMD gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --worker-class gthread
