#!/bin/bash

echo "=== System Status ==="
echo ""

echo "📊 Agents:"
ps aux | grep -E "(data_analysis_agent|cs_feedback_agent|game_balance_agent)" | grep -v grep | awk '{print "  ✅", $11, "(PID:", $2")"}'

echo ""
echo "🎨 GUIs:"
ps aux | grep -E "streamlit.*gui" | grep -v grep | awk '{print "  ✅", $13, $14, "(PID:", $2")"}'

echo ""
echo "🌐 URLs:"
echo "  📊 Data Agent GUI:    http://localhost:8503"
echo "  💬 CS Agent GUI:      http://localhost:8502"
echo "  ⚖️  Balance Agent GUI: http://localhost:8501"

echo ""
echo "🔍 Kafka:"
docker ps | grep kafka | awk '{print "  ✅ Kafka running (Container:", $1")"}'
