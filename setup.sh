#!/bin/bash
set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   ClauseLens — First-time setup      ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Check required tools ──────────────────────────────────────────────────────

check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo "❌ '$1' is not installed."
    echo "   $2"
    exit 1
  fi
}

check_command node  "Install Node.js from https://nodejs.org (choose the LTS version)"
check_command python3 "Install Python from https://www.python.org/downloads/"

NODE_VERSION=$(node -v | cut -d. -f1 | sed 's/v//')
if [ "$NODE_VERSION" -lt 18 ]; then
  echo "❌ Node.js 18+ required. You have $(node -v). Download from https://nodejs.org"
  exit 1
fi

echo "✅ Node.js $(node -v)"
echo "✅ Python $(python3 --version)"

# ── Check .env files are filled in ───────────────────────────────────────────

if grep -v "^#" apps/api/.env | grep -q "YOUR_SUPABASE\|YOUR_OPENAI"; then
  echo ""
  echo "❌ Please fill in your Supabase credentials in apps/api/.env first."
  echo "   See the README for how to get these from supabase.com"
  exit 1
fi

# ── Install pnpm ──────────────────────────────────────────────────────────────

if ! command -v pnpm &> /dev/null; then
  echo "📦 Installing pnpm..."
  npm install -g pnpm
fi
echo "✅ pnpm $(pnpm -v)"

# ── Install Node dependencies ─────────────────────────────────────────────────

echo ""
echo "📦 Installing Node.js dependencies..."
pnpm install

echo "📦 Building shared package..."
pnpm --filter @clauselens/shared build

# ── Set up Python virtual environment ────────────────────────────────────────

echo ""
echo "🐍 Setting up Python environment..."
cd apps/api

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "✅ Python dependencies installed"

cd ../..

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ Setup complete!                                       ║"
echo "║                                                          ║"
echo "║  One more step — set up the database:                    ║"
echo "║                                                          ║"
echo "║  1. Open supabase.com → your project                     ║"
echo "║  2. Click 'SQL Editor' in the left sidebar               ║"
echo "║  3. Click 'New query'                                     ║"
echo "║  4. Open the file 'schema.sql' in this folder            ║"
echo "║     and paste ALL its contents into the editor           ║"
echo "║  5. Click 'Run'                                          ║"
echo "║                                                          ║"
echo "║  Then run:  ./start.sh                                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
