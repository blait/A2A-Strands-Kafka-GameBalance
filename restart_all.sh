#!/bin/bash
# Complete restart script for Kafka, agents, and GUIs

set -e  # Exit on error

cd "$(dirname "$0")"

echo "🛑 Stopping all services..."
pkill -f "game_balance_agent|data_analysis_agent|cs_feedback_agent|streamlit" || true
sleep 2

echo "🐳 Checking Docker..."
if ! docker ps > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

echo "📦 Starting Kafka..."
docker compose up -d
sleep 5

echo "📋 Creating Kafka topics..."
venv/bin/python scripts/create_topics.py

echo "🚀 Starting agents..."
# Start agents in order
venv/bin/python -u agents/data_analysis_agent.py > /tmp/data_agent.log 2>&1 &
venv/bin/python -u agents/cs_feedback_agent.py > /tmp/cs_agent.log 2>&1 &
sleep 3
venv/bin/python -u agents/game_balance_agent.py > /tmp/balance_agent.log 2>&1 &

echo "⏳ Waiting for agents to start..."
sleep 5

echo "🎨 Starting GUIs..."
venv/bin/streamlit run gui/balance_gui.py --server.port 8501 > /tmp/balance_gui.log 2>&1 &
venv/bin/streamlit run gui/cs_gui.py --server.port 8502 > /tmp/cs_gui.log 2>&1 &
venv/bin/streamlit run gui/analysis_gui.py --server.port 8503 > /tmp/analysis_gui.log 2>&1 &

echo "⏳ Waiting for GUIs to start..."
sleep 5

echo ""
echo "✅ All services started!"
echo ""
echo "📊 Agents:"
echo "  - Balance Agent: http://localhost:9001"
echo "  - Data Agent: http://localhost:9003"
echo "  - CS Agent: http://localhost:9002"
echo ""
echo "🎨 GUIs:"
echo "  - Balance GUI: http://localhost:8501"
echo "  - CS GUI: http://localhost:8502"
echo "  - Analysis GUI: http://localhost:8503"
echo ""
echo "📝 Logs:"
echo "  - tail -f /tmp/balance_agent.log"
echo "  - tail -f /tmp/data_agent.log"
echo "  - tail -f /tmp/cs_agent.log"
echo ""
echo "🛑 To stop all services:"
echo "  - ./stop_all.sh"

