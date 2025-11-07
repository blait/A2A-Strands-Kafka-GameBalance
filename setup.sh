#!/bin/bash
# Initial setup script - Run this once before first use

set -e  # Exit on error

cd "$(dirname "$0")"

echo "🔧 Game Balance A2A System - Initial Setup"
echo "=========================================="
echo ""

# Check Python
echo "1️⃣ Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION found"

# Check Docker
echo ""
echo "2️⃣ Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker Desktop."
    exit 1
fi
if ! docker ps > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi
echo "✅ Docker is running"

# Create virtual environment
echo ""
echo "3️⃣ Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Install packages
echo ""
echo "4️⃣ Installing Python packages..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Packages installed"

# Create .env file
echo ""
echo "5️⃣ Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ .env file created"
else
    echo "✅ .env file already exists"
fi

# Start Kafka
echo ""
echo "6️⃣ Starting Kafka..."
docker compose up -d
sleep 5
echo "✅ Kafka started"

# Create topics
echo ""
echo "7️⃣ Creating Kafka topics..."
venv/bin/python scripts/create_topics.py
echo "✅ Topics created"

echo ""
echo "=========================================="
echo "✅ Setup completed successfully!"
echo ""
echo "🚀 Next steps:"
echo "  1. Start all services: ./restart_all.sh"
echo "  2. Run tests: source venv/bin/activate && python test_kafka_a2a.py"
echo "  3. Stop services: ./stop_all.sh"
echo ""
echo "📖 For more information, see README.md"
