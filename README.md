# MSK A2A Demo - 게임 밸런스 자동화 시스템

Google A2A 프로토콜과 Kafka를 활용한 Hub-Spoke 아키텍처 데모

## 🎯 프로젝트 개요

게임 밸런스 조정을 위한 AI 에이전트들이 Kafka를 통해 통신하는 시스템입니다.

- **Balance Agent**: 코디네이터 역할, 다른 에이전트들을 호출하여 종합 분석
- **Data Agent**: 게임 통계 데이터 분석 (승률, 게임 시간 등)
- **CS Agent**: 게시판 컴플레인 수집 및 분석 (예정)

## ✨ 주요 기능

### ✅ 완성된 기능

1. **Kafka 기반 Agent 간 통신**
   - Balance Agent ↔ Data/CS Agent 완전 작동
   - Request/Response 토픽을 통한 비동기 메시징
   - Agent Registry를 통한 동적 Agent 발견

2. **Multi-turn 대화 지원**
   - `input-required` 상태로 추가 정보 요청
   - Context 유지를 통한 연속 대화
   - 예시: "승률?" → "어떤 종족?" → "저그" → "저그 승률 50%"

3. **A2A 프로토콜 구현**
   - Task 기반 상태 관리 (completed, input-required, failed)
   - Artifact를 통한 응답 전달
   - Event Queue를 통한 비동기 처리

## 🏗️ 아키텍처

### Hub-Spoke 구조

```
                    ┌─────────────────┐
                    │   Kafka Hub     │
                    │   (localhost)   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Balance Agent │    │  Data Agent   │    │   CS Agent    │
│   (port 9001) │    │  (port 9003)  │    │  (port 9002)  │
│               │    │               │    │               │
│ - 코디네이터     │    │ - 승률 분석     │    │ - 컴플레인      │
│ - Tool 호출    │    │ - 게임시간      │    │   (예정)        │
└───────────────┘    └───────────────┘    └───────────────┘
```

### Kafka Topics

```
agent.balance.requests    → Balance Agent로 요청
agent.balance.responses   → Balance Agent의 응답

agent.data.requests       → Data Agent로 요청
agent.data.responses      → Data Agent의 응답

agent.registry            → Agent 등록 정보
```

## 🚀 빠른 시작

### 최초 설정 (한 번만 실행)

```bash
# 모든 초기 설정 자동 실행 (Python 패키지, Kafka, 토픽 생성)
./setup.sh
```

이 스크립트는 다음을 자동으로 수행합니다:
- Python 가상환경 생성
- 필요한 패키지 설치 (requirements.txt)
- .env 파일 생성
- Kafka 시작
- Kafka 토픽 생성

### 방법 1: 자동 실행 (권장)

```bash
# 모든 서비스 시작 (Agents + GUIs)
./restart_all.sh

# 모든 서비스 종료
./stop_all.sh
```

### 방법 2: 수동 실행

#### 0. 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# 로컬 개발 시 (기본값 사용)
# KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# AWS MSK 사용 시
# KAFKA_BOOTSTRAP_SERVERS=b-1.your-cluster.xxxxx.kafka.region.amazonaws.com:9092
```

#### 1. Kafka 실행

```bash
docker compose up -d
```

#### 2. 토픽 생성

```bash
python scripts/create_topics.py
```

#### 3. Agent 실행

```bash
# Terminal 1: Data Agent
python agents/data_analysis_agent.py

# Terminal 2: Balance Agent
python agents/game_balance_agent.py
```




## 📁 프로젝트 구조

```
game-balance-a2a/
├── agents/
│   ├── game_balance_agent.py          # Balance Agent (코디네이터)
│   ├── game_balance_agent_executor.py # Balance Agent 실행 로직
│   ├── data_analysis_agent.py         # Data Agent
│   └── data_analysis_agent_executor.py # Data Agent 실행 로직
├── kafka/
│   ├── kafka_transport.py             # Kafka 기반 A2A Transport
│   ├── kafka_consumer_handler.py      # Kafka Consumer 핸들러
│   └── agent_registry.py              # Agent 등록/발견
├── scripts/
│   └── create_topics.py               # Kafka 토픽 생성
├── docker-compose.yml                 # Kafka 로컬 환경
└── test_kafka_a2a.py                  # 테스트 스크립트
```

## 🔄 메시지 흐름

### 단순 질문 (Single-turn)

```
Client
  ↓ "테란 승률 알려줘"
Balance Agent (Kafka Consumer)
  ↓ Tool 호출
Data Agent (Kafka Consumer)
  ↓ 승률 분석
Balance Agent
  ↓ 응답 생성
Client
  ✅ "테란의 승률은 100.0%입니다"
```

### 복잡한 질문 (Multi-turn)

```
Client
  ↓ "승률?"
Balance Agent → Data Agent
  ↓ input_required
Client
  ✅ "어떤 종족의 승률을 알고 싶으신가요?"
  
Client
  ↓ "저그" (같은 context)
Balance Agent → Data Agent
  ↓ 승률 분석
Client
  ✅ "저그의 승률은 50.0%입니다"
```

## 🛠️ 기술 스택

- **Language**: Python 3.13
- **Agent Framework**: Strands
- **LLM**: Amazon Bedrock (Nova Lite)
- **Message Broker**: Apache Kafka (Docker)
- **A2A Protocol**: Google A2A
- **Async**: aiokafka, asyncio



