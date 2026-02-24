#!/bin/bash

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   ClauseLens — Starting...           ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Check setup has been run ─────────────────────────────────────────────────

if [ ! -f "apps/api/.venv/bin/activate" ]; then
  echo "❌ Setup hasn't been run yet. Please run first:"
  echo ""
  echo "   ./setup.sh"
  echo ""
  exit 1
fi

# ── Kill any previously running API/web processes ────────────────────────────

echo "🔄 Stopping any existing processes on ports 8000 and 3000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
sleep 1

# ── Start API ─────────────────────────────────────────────────────────────────

cd apps/api
source .venv/bin/activate

echo "🚀 Starting API on http://localhost:8000 ..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

cd ../..

# ── Wait for API to be ready ──────────────────────────────────────────────────

echo "   Waiting for API..."
for i in {1..30}; do
  if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ API is ready"
    break
  fi
  sleep 1
done

# ── Start Web ─────────────────────────────────────────────────────────────────

echo ""
echo "🌐 Starting web app on http://localhost:3000 ..."
echo ""
echo "   Press Ctrl+C to stop everything."
echo ""

trap "echo ''; echo 'Stopping...'; kill $API_PID 2>/dev/null; exit" INT TERM

cd apps/web
pnpm dev
