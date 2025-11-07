# 🚀 Quick Start Guide

## Prerequisites

- Python 3.9 or higher
- Docker Desktop (running)

## Installation (First Time Only)

```bash
# Clone the repository
git clone <repository-url>
cd game-balance-a2a

# Run setup script (installs everything)
./setup.sh
```

This will:
- ✅ Create Python virtual environment
- ✅ Install all required packages
- ✅ Create .env configuration file
- ✅ Start Kafka
- ✅ Create Kafka topics

## Daily Usage

### Start Everything

```bash
./restart_all.sh
```

This starts:
- 🐳 Kafka (if not running)
- 🤖 3 AI Agents (Balance, Data, CS)
- 🎨 3 Web GUIs (ports 8501, 8502, 8503)

### Access the System

**Web GUIs:**
- Balance GUI: http://localhost:8501
- CS GUI: http://localhost:8502
- Analysis GUI: http://localhost:8503

**Agent APIs:**
- Balance Agent: http://localhost:9001
- Data Agent: http://localhost:9003
- CS Agent: http://localhost:9002

### Test the System

```bash
source venv/bin/activate
python test_kafka_a2a.py
```

### Stop Everything

```bash
./stop_all.sh
```

## Troubleshooting

### Docker not running
```bash
# Start Docker Desktop manually, then run:
./restart_all.sh
```

### Packages not installed
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Kafka topics missing
```bash
source venv/bin/activate
python scripts/create_topics.py
```

### Check logs
```bash
tail -f /tmp/balance_agent.log
tail -f /tmp/data_agent.log
tail -f /tmp/cs_agent.log
```

## Configuration

Edit `.env` file to customize:
```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Agent ports
BALANCE_AGENT_PORT=9001
DATA_AGENT_PORT=9003
CS_AGENT_PORT=9002
```

## For AWS MSK

Edit `.env`:
```bash
KAFKA_BOOTSTRAP_SERVERS=b-1.your-cluster.xxxxx.kafka.region.amazonaws.com:9092
```

Then restart:
```bash
./restart_all.sh
```
