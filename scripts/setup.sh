#!/usr/bin/env bash
# =============================================================================
# scripts/setup.sh — one-time local dev setup
# =============================================================================
set -euo pipefail

echo "🚀 SEO Agent — Local Dev Setup"
echo "================================"

# Check requirements
command -v docker >/dev/null 2>&1 || { echo "❌ Docker not found. Install Docker Desktop first."; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "❌ docker compose not found."; exit 1; }

# Copy env if missing
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✅ Created .env from .env.example — fill in your API keys before running"
else
  echo "✅ .env already exists"
fi

# Start infrastructure only first (no app workers yet)
echo ""
echo "📦 Starting infrastructure services..."
docker compose up -d postgres redis clickhouse minio

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 8

# Run DB migrations
echo ""
echo "🗄️  Running database migrations..."
docker compose run --rm api alembic upgrade head

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your API keys (ANTHROPIC_API_KEY, DATAFORSEO_*, GSC_*)"
echo "  2. Run: docker compose up"
echo "  3. Open: http://localhost:3000  (frontend)"
echo "  4. Open: http://localhost:8000/docs  (API docs)"
echo "  5. Open: http://localhost:5555  (Celery Flower — task monitor)"
echo "  6. Open: http://localhost:9001  (MinIO console — content storage)"
