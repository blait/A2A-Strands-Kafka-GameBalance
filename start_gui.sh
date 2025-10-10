#!/bin/bash

cd "$(dirname "$0")"

echo "🎨 Starting GUI interfaces..."
echo ""
echo "  📊 Data Agent GUI:    http://localhost:8503"
echo "  💬 CS Agent GUI:      http://localhost:8502"
echo "  ⚖️  Balance Agent GUI: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop all GUIs"
echo ""

# Start all GUIs
./venv/bin/streamlit run gui/analysis_gui.py --server.port 8503 &
PID1=$!

./venv/bin/streamlit run gui/cs_gui.py --server.port 8502 &
PID2=$!

./venv/bin/streamlit run gui/balance_gui.py --server.port 8501 &
PID3=$!

# Wait for Ctrl+C
trap "echo ''; echo '🛑 Stopping all GUIs...'; kill $PID1 $PID2 $PID3 2>/dev/null; exit" INT
wait
