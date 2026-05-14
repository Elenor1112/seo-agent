FROM python:3.12-slim

WORKDIR /app

# All system deps in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl wget gnupg ca-certificates \
    libpq-dev libxml2-dev libxslt1-dev \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libxfixes3 libcairo2 libpixman-1-0 \
    fonts-liberation fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright — skip install-deps, use PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD workaround
RUN pip install playwright \
    && PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 playwright install chromium

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1