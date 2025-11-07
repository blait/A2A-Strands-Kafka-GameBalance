#!/bin/bash
# Stop all services

echo "🛑 Stopping all agents and GUIs..."
pkill -f "game_balance_agent|data_analysis_agent|cs_feedback_agent|streamlit" || true

echo "🐳 Stopping Kafka..."
cd "$(dirname "$0")"
docker compose down

echo "✅ All services stopped!"
