#!/bin/bash

# MeMeIt Robust Startup Script v5

# 0. Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# 1. Kill existing processes to prevent port conflicts and zombie workers
cleanup_zombies() {
    echo "🧹 Cleaning up old processes and state..."
    pkill -9 -f "huey_consumer" 2>/dev/null
    pkill -9 -f "graduation_scraper" 2>/dev/null
    pkill -9 -f "graduation_wss" 2>/dev/null
    pkill -9 -f "bot\.py" 2>/dev/null
    pkill -9 -f "api\.py" 2>/dev/null
    pkill -9 -f "graduation_ai\.py" 2>/dev/null
    pkill -9 -f "vite" 2>/dev/null
    pkill -9 -f "bootstrap.py" 2>/dev/null
    PORT_PID=$(lsof -t -i:5173 2>/dev/null)
    [ ! -z "$PORT_PID" ] && kill -9 $PORT_PID 2>/dev/null
    PORT_API=$(lsof -t -i:8000 2>/dev/null)
    [ ! -z "$PORT_API" ] && kill -9 $PORT_API 2>/dev/null
    # Clear Redis state
    redis-cli flushall >/dev/null 2>&1
    sleep 1
}

cleanup_zombies

# Trap for Ctrl+C
cleanup() {
    echo -e "\n🛑 Shutting down MeMeIt..."
    cleanup_zombies
    exit
}
trap cleanup SIGINT SIGTERM

echo "🚀 Starting MeMeIt Risks Platform..."

# 2. Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../venv" ]; then
    source ../venv/bin/activate
else
    echo "❌ venv not found."
    exit 1
fi

pip install redis >/dev/null 2>&1

# 3. Check for Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo "⚠️  Redis is not running. Starting..."
    redis-server --daemonize yes
    sleep 1
fi

mkdir -p data
export PYTHONPATH=$PYTHONPATH:.

# 5. Start Huey Workers (Isolated Architecture)
echo "📥 Starting Monitoring Worker (8 threads)..."
huey_consumer src.workers.default_huey -w 8 > data/huey_default.log 2>&1 &
echo "🏎️ Starting Intake Worker (2 threads - DEDICATED FAST LANE)..."
huey_consumer src.workers.intake_huey -w 2 > data/huey_intake.log 2>&1 &
HUEY_PID=$!

# 6. Start FastAPI Backend
echo "🔌 Starting API (Port 8000)..."
python3 src/api.py > data/api.log 2>&1 &
API_PID=$!

# Start Automatic Ingestion
echo "📡 Starting Automated Token Scrapers..."
python3 src/graduation_scraper.py > data/scraper.log 2>&1 &
python3 src/graduation_wss.py > data/wss.log 2>&1 &

# 7. Bootstrap existing tokens (Resume monitoring)
sleep 2
echo "🔄 Resuming monitoring for existing tokens..."
python3 src/bootstrap.py || true

# 7. Start Dashboard
echo "🖥️ Starting Web Dashboard (Port 5173)..."
if [ -d "dashboard" ]; then
    (cd dashboard && npm run dev) > data/dashboard.log 2>&1 &
    DASH_PID=$!
fi

sleep 2
echo "----------------------------------------"
echo "✅ All services started!"
echo "----------------------------------------"

# 8. Start Telegram Bot in foreground
python3 src/bot.py
