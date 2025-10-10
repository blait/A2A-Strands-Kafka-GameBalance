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
   - Balance Agent ↔ Data Agent 완전 작동
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
│ - 코디네이터   │    │ - 승률 분석    │    │ - 컴플레인    │
│ - Tool 호출   │    │ - 게임시간     │    │   (예정)      │
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

### 1. Kafka 실행

```bash
docker-compose up -d
```

### 2. 토픽 생성

```bash
python scripts/create_topics.py
```

### 3. Agent 실행

```bash
# Terminal 1: Data Agent
python agents/data_analysis_agent.py

# Terminal 2: Balance Agent
python agents/game_balance_agent.py
```

### 4. 테스트

```bash
# 단순 질문
python test_kafka_a2a.py

# Multi-turn 대화 테스트
python -c "
import asyncio
from kafka.kafka_transport import KafkaTransport
from a2a.types import Message, Part, TextPart, Role, MessageSendParams
from uuid import uuid4
import json

async def test():
    transport = KafkaTransport(target_agent_name='balance')
    
    # Turn 1: 모호한 질문
    msg1 = Message(kind='message', role=Role.user, 
                   parts=[Part(TextPart(kind='text', text='승률?'))], 
                   message_id=uuid4().hex)
    result1 = await transport.send_message(MessageSendParams(message=msg1))
    
    print(f'Turn 1 - State: {result1.status.state}')
    data1 = json.loads(result1.artifacts[0].parts[0].root.text)
    print(f'Message: {data1[\"message\"]}')
    
    # Turn 2: 종족 제공
    if result1.status.state == 'input-required':
        msg2 = Message(kind='message', role=Role.user,
                       parts=[Part(TextPart(kind='text', text='저그'))],
                       message_id=uuid4().hex,
                       context_id=result1.context_id)
        result2 = await transport.send_message(MessageSendParams(message=msg2))
        
        print(f'Turn 2 - State: {result2.status.state}')
        data2 = json.loads(result2.artifacts[0].parts[0].root.text)
        print(f'Message: {data2[\"message\"]}')
    
    await transport.close()

asyncio.run(test())
"
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

## 📊 테스트 결과

✅ Balance Agent Kafka 통신  
✅ Data Agent Kafka 통신  
✅ Agent 간 Tool 호출  
✅ Multi-turn 대화 (input-required)  
✅ Artifact 전송  
✅ Context 유지  

## 🔜 향후 계획

- [ ] CS Agent 구현
- [ ] AWS MSK 배포
- [ ] GUI 개선
- [ ] 에러 핸들링 강화
- [ ] 모니터링 대시보드

## 📝 라이선스

MIT License
