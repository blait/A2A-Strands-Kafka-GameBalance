# Kafka Transport Layer 구현 계획

## 목표

A2A 프로토콜을 유지하면서 HTTP 대신 Kafka를 전송 레이어로 사용

## 아키텍처

```
Balance Agent (A2A Client with KafkaTransport)
    ↓ Kafka Produce
Kafka Hub (MSK)
    ↓ Kafka Consume
Data/CS Agent (KafkaConsumerHandler)
    ↓ Kafka Produce (response)
Kafka Hub
    ↓ Kafka Consume
Balance Agent (response received)
```

## 장점

✅ **A2A 기능 완전 유지**
- 실시간 thinking 스트리밍
- 멀티턴 대화
- 동기/비동기 모두 지원

✅ **에이전트 코드 변경 최소**
- Transport만 교체
- 비즈니스 로직 그대로

✅ **확장성**
- N² → N+M 연결
- 에이전트 추가 시 선형 증가

✅ **메시지 영속성**
- 모든 통신 Kafka에 기록
- 감사 로그, 디버깅, 재생 가능

✅ **느슨한 결합**
- 에이전트 간 URL 불필요
- 장애 격리

## 구현 단계

### Phase 1: Kafka 인프라 (1-2시간)

#### 1.1 로컬 Kafka 설정
```bash
# docker-compose.yml
version: '3'
services:
  kafka:
    image: confluentinc/cp-kafka:latest
    ports:
      - "9092:9092"
    environment:
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
```

#### 1.2 Topic 생성
```bash
# Topics
- agent.data.requests
- agent.data.responses
- agent.cs.requests
- agent.cs.responses
- agent.balance.requests
- agent.balance.responses
```

### Phase 2: KafkaTransport 구현 (3-4시간)

#### 2.1 파일 구조
```
game-balance-a2a/
├── kafka/
│   ├── __init__.py
│   ├── kafka_transport.py           # ClientTransport 구현 (Producer)
│   ├── kafka_consumer_handler.py    # Server-side Consumer (요청 처리)
│   └── config.py                    # Kafka 설정
```

#### 2.2 KafkaTransport 클래스 (Client-side)
```python
# kafka/kafka_transport.py
from a2a.client.transports.base import ClientTransport
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import json
import uuid

class KafkaTransport(ClientTransport):
    def __init__(self, agent_name: str, bootstrap_servers: str):
        self.agent_name = agent_name
        self.bootstrap_servers = bootstrap_servers
        self.producer = None
        self.consumer = None
        self.pending_requests = {}  # correlation_id -> asyncio.Future
    
    async def send_message_streaming(self, request, context=None):
        # 1. Correlation ID 생성
        correlation_id = str(uuid.uuid4())
        
        # 2. Kafka에 요청 발행
        await self.producer.send(
            f'agent.{self.agent_name}.requests',
            key=correlation_id.encode(),
            value=json.dumps(request).encode()
        )
        
        # 3. 응답 topic 구독 (스트리밍)
        async for msg in self.consumer:
            if msg.key.decode() == correlation_id:
                event = json.loads(msg.value.decode())
                yield event
                
                # 완료 이벤트면 종료
                if event.get('final'):
                    break
```

#### 2.3 주요 메서드 구현
- `send_message()` - 동기 메시지 전송
- `send_message_streaming()` - 스트리밍 메시지 전송
- `get_task()` - Task 조회
- `cancel_task()` - Task 취소
- `get_card()` - AgentCard 조회

### Phase 3: Server-Side Kafka Integration (2-3시간)

#### 3.1 KafkaConsumerHandler 클래스 (Server-side)
```python
# kafka/kafka_consumer_handler.py
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

class KafkaConsumerHandler:
    """
    Kafka Consumer를 실행하여 요청을 받고 A2A Executor로 처리
    주의: Kafka 브로커 서버가 아니라 Consumer 역할만 수행
    """
    def __init__(self, agent_name: str, agent_executor):
        self.agent_name = agent_name
        self.agent_executor = agent_executor
        self.consumer = None
        self.producer = None
    
    async def start(self):
        # Kafka Consumer 시작 (요청 topic 구독)
        self.consumer = AIOKafkaConsumer(
            f'agent.{self.agent_name}.requests',
            bootstrap_servers='localhost:9092'
        )
        await self.consumer.start()
        
        # Producer 시작 (응답 발행용)
        self.producer = AIOKafkaProducer(
            bootstrap_servers='localhost:9092'
        )
        await self.producer.start()
        
        # 메시지 처리 루프
        async for msg in self.consumer:
            await self.handle_request(msg)
    
    async def handle_request(self, msg):
        correlation_id = msg.key.decode()
        request = json.loads(msg.value.decode())
        
        # A2A Executor 실행
        async for event in self.agent_executor.execute(request):
            # 응답을 Kafka에 발행
            await self.producer.send(
                f'agent.{self.agent_name}.responses',
                key=correlation_id.encode(),
                value=json.dumps(event).encode()
            )
```

### Phase 4: 에이전트 수정 (1-2시간)

#### 4.1 Balance Agent (Client)
```python
# agents/game_balance_agent.py

# 기존
from a2a.client import ClientFactory, ClientConfig
config = ClientConfig(httpx_client=client, streaming=False)

# 변경
from kafka.kafka_transport import KafkaTransport
transport = KafkaTransport(agent_name="balance", bootstrap_servers="localhost:9092")
config = ClientConfig(transport=transport, streaming=True)
```

#### 4.2 Data/CS Agent (Server)
```python
# agents/data_analysis_agent.py

# 기존 (HTTP 서버)
a2a_server = A2AStarletteApplication(...)
uvicorn.run(app, host="0.0.0.0", port=9003)

# 추가 (Kafka Consumer)
from kafka.kafka_consumer_handler import KafkaConsumerHandler

# 백그라운드에서 Kafka 요청 처리
consumer_handler = KafkaConsumerHandler("data", DataAnalysisExecutor())
asyncio.create_task(consumer_handler.start())

# HTTP 서버도 유지 가능 (선택사항)
uvicorn.run(app, host="0.0.0.0", port=9003)
```

### Phase 5: 테스트 (2-3시간)

#### 5.1 단위 테스트
```python
# tests/test_kafka_transport.py
async def test_send_message():
    transport = KafkaTransport("test", "localhost:9092")
    response = await transport.send_message(msg)
    assert response is not None

async def test_streaming():
    transport = KafkaTransport("test", "localhost:9092")
    events = []
    async for event in transport.send_message_streaming(msg):
        events.append(event)
    assert len(events) > 0
```

#### 5.2 통합 테스트
```python
# tests/test_kafka_integration.py
async def test_balance_to_data():
    # Balance Agent → Kafka → Data Agent
    response = await balance_agent.call_data_agent("테란 승률?")
    assert "승률" in response
```

#### 5.3 GUI 테스트
- 실시간 thinking 표시 확인
- 멀티턴 대화 확인
- 에러 처리 확인

### Phase 6: MSK 배포 (선택사항)

#### 6.1 Terraform으로 MSK 생성
```hcl
# infrastructure/terraform/msk.tf
resource "aws_msk_cluster" "game_balance" {
  cluster_name = "game-balance-kafka"
  kafka_version = "3.5.1"
  number_of_broker_nodes = 3
}
```

#### 6.2 설정 변경
```python
# 로컬
bootstrap_servers = "localhost:9092"

# MSK
bootstrap_servers = "b-1.gamebalance.xxx.kafka.us-east-1.amazonaws.com:9092"
```

## 구현 우선순위

### MVP (Minimum Viable Product)
1. ✅ KafkaTransport 기본 구현 (send_message, send_message_streaming)
2. ✅ KafkaConsumerHandler 기본 구현
3. ✅ Balance → Data Agent 단방향 테스트
4. ✅ 실시간 thinking 스트리밍 확인

### 추가 기능
5. ⚠️ 멀티턴 대화 지원
6. ⚠️ 에러 처리 & 재시도
7. ⚠️ Task 관리 (get_task, cancel_task)
8. ⚠️ AgentCard 동적 조회

### 프로덕션
9. 🔲 MSK 배포
10. 🔲 모니터링 & 로깅
11. 🔲 성능 최적화
12. 🔲 보안 (SSL, SASL)

## 예상 일정

- **Phase 1-2 (MVP)**: 1일
- **Phase 3-4 (통합)**: 1일
- **Phase 5 (테스트)**: 0.5일
- **Phase 6 (MSK)**: 1일

**총 예상 시간: 3-4일**

## 기술 스택

- **Kafka Client**: aiokafka
- **A2A Protocol**: 기존 a2a 라이브러리
- **Serialization**: JSON
- **Async Framework**: asyncio

## 리스크 & 대응

### 리스크 1: Correlation ID 관리 복잡
**대응**: 간단한 dict 기반 매칭 (MVP), 나중에 Redis로 확장

### 리스크 2: 스트리밍 성능
**대응**: Kafka Consumer 설정 최적화 (fetch_min_bytes, fetch_max_wait_ms)

### 리스크 3: 에러 처리
**대응**: Dead Letter Queue + 재시도 로직

### 리스크 4: 멀티턴 상태 관리
**대응**: Kafka Streams로 상태 저장 or Redis 사용

## 성공 기준

✅ Balance Agent가 Kafka를 통해 Data/CS Agent 호출
✅ 실시간 thinking 스트리밍 작동
✅ 멀티턴 대화 작동
✅ 에이전트 코드 변경 최소 (Transport만 교체)
✅ 기존 GUI 그대로 작동

## 다음 단계

1. Kafka 로컬 환경 구축
2. KafkaTransport 기본 구현
3. 단순 메시지 전송 테스트
4. 스트리밍 구현
5. 전체 통합 테스트

## 용어 정리

- **Kafka 브로커**: 실제 Kafka 서버 (docker-compose로 실행)
- **KafkaTransport**: Client-side Producer (요청 발행)
- **KafkaConsumerHandler**: Server-side Consumer (요청 수신 및 처리)
