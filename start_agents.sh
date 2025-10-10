#!/bin/bash

cd "$(dirname "$0")"

echo "🛑 Stopping existing agents..."
pkill -f "python.*agent.py" 2>/dev/null
sleep 2

echo "🧹 Cleaning logs..."
rm -f data_agent.log cs_agent.log balance_agent.log

echo "🚀 Starting Data Agent..."
./venv/bin/python agents/data_analysis_agent.py > data_agent.log 2>&1 &
DATA_PID=$!
echo "   PID: $DATA_PID"
sleep 4

echo "🚀 Starting CS Agent..."
./venv/bin/python agents/cs_feedback_agent.py > cs_agent.log 2>&1 &
CS_PID=$!
echo "   PID: $CS_PID"
sleep 4

echo "🚀 Starting Balance Agent..."
./venv/bin/python agents/game_balance_agent.py > balance_agent.log 2>&1 &
BALANCE_PID=$!
echo "   PID: $BALANCE_PID"
sleep 4

echo ""
echo "✅ All agents started"
echo ""
echo "=== Port Status ==="
lsof -i :9001 -i :9002 -i :9003 2>/dev/null | grep LISTEN || echo "⚠️  No ports listening yet"
echo ""
echo "=== Process Status ==="
ps aux | grep "python.*agent.py" | grep -v grep || echo "⚠️  No agent processes found"
