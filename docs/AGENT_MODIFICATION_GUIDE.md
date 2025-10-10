# 에이전트 Kafka Transport 적용 가이드

## 수정 개요

1. **Balance Agent (Client)**: HTTP → Kafka Transport 교체
2. **Data/CS Agent (Server)**: Kafka Consumer 추가

---

## 1. Balance Agent 수정

### 변경 전 (HTTP)
```python
# agents/game_balance_agent.py

class A2AClient:
    def __init__(self):
        self.agents = {
            "data": "http://localhost:9003",
            "cs": "http://localhost:9002"
        }
    
    async def call_agent(self, agent_name: str, query: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            config = ClientConfig(httpx_client=client, streaming=False)
            factory = ClientFactory(config)
            a2a_client = factory.create(self.cards[agent_name])
            # ...
```

### 변경 후 (Kafka)
```python
# agents/game_balance_agent.py
from kafka.kafka_transport import KafkaTransport

class A2AClient:
    def __init__(self):
        self.agents = {
            "data": "data",  # agent name만 필요
            "cs": "cs"
        }
        self.transports = {}
    
    async def init(self):
        # Kafka Transport 생성
        for name in self.agents.keys():
            self.transports[name] = KafkaTransport(
                target_agent_name=name,
                bootstrap_servers="localhost:9092"
            )
            print(f"✅ Kafka transport ready for {name} agent")
    
    async def call_agent(self, agent_name: str, query: str) -> str:
        if agent_name not in self.transports:
            return f"Agent {agent_name} not available"
        
        print(f"\n📤 [Kafka Request] Calling {agent_name} agent")
        print(f"   Query: {query}")
        
        try:
            # Kafka Transport 사용
            transport = self.transports[agent_name]
            
            msg = Message(
                kind="message",
                role=Role.user,
                parts=[Part(TextPart(kind="text", text=query))],
                message_id=uuid4().hex
            )
            
            # send_message 호출
            result = await transport.send_message(
                MessageSendParams(message=msg)
            )
            
            # 응답 처리
            if hasattr(result, 'artifacts') and result.artifacts:
                return result.artifacts[0].parts[0].text
            return "No response"
            
        except Exception as e:
            print(f"❌ Error calling {agent_name}: {e}")
            return f"Error: {e}"
```

### 스트리밍 버전 (선택사항)
```python
async def call_agent_streaming(self, agent_name: str, query: str):
    """실시간 thinking 스트리밍"""
    transport = self.transports[agent_name]
    
    msg = Message(
        kind="message",
        role=Role.user,
        parts=[Part(TextPart(kind="text", text=query))],
        message_id=uuid4().hex
    )
    
    async for event in transport.send_message_streaming(
        MessageSendParams(message=msg)
    ):
        if isinstance(event, TaskArtifactUpdateEvent):
            yield event.artifact.parts[0].text
```

---

## 2. Data Agent 수정 (Server-side)

### 변경 전 (HTTP만)
```python
# agents/data_analysis_agent.py

if __name__ == "__main__":
    # HTTP 서버만 실행
    uvicorn.run(app, host="0.0.0.0", port=9003)
```

### 변경 후 (HTTP + Kafka)
```python
# agents/data_analysis_agent.py
import asyncio
from kafka.kafka_consumer_handler import KafkaConsumerHandler
from data_analysis_agent_executor import DataAnalysisExecutor

async def start_kafka_consumer():
    """Kafka Consumer 시작"""
    consumer = KafkaConsumerHandler(
        agent_name="data",
        agent_executor=DataAnalysisExecutor(),
        bootstrap_servers="localhost:9092"
    )
    await consumer.start()

if __name__ == "__main__":
    # Kafka Consumer를 백그라운드에서 실행
    import threading
    
    def run_kafka():
        asyncio.run(start_kafka_consumer())
    
    kafka_thread = threading.Thread(target=run_kafka, daemon=True)
    kafka_thread.start()
    
    # HTTP 서버도 유지 (선택사항)
    uvicorn.run(app, host="0.0.0.0", port=9003)
```

### Kafka만 사용 (HTTP 제거)
```python
if __name__ == "__main__":
    # Kafka Consumer만 실행
    asyncio.run(start_kafka_consumer())
```

---

## 3. CS Agent 수정 (동일한 패턴)

```python
# agents/cs_feedback_agent.py
from kafka.kafka_consumer_handler import KafkaConsumerHandler
from cs_feedback_agent_executor import CSFeedbackExecutor

async def start_kafka_consumer():
    consumer = KafkaConsumerHandler(
        agent_name="cs",
        agent_executor=CSFeedbackExecutor(),
        bootstrap_servers="localhost:9092"
    )
    await consumer.start()

if __name__ == "__main__":
    asyncio.run(start_kafka_consumer())
```

---

## 4. Executor 수정 (필요 시)

KafkaConsumerHandler가 호출하는 메서드:
- `send_message(params)` - 동기 메시지
- `send_message_streaming(params)` - 스트리밍 메시지
- `get_task(params)` - Task 조회
- `cancel_task(params)` - Task 취소

현재 Executor가 이 메서드들을 지원하는지 확인 필요.

### 예시: Executor 인터페이스
```python
class DataAnalysisExecutor:
    async def send_message(self, params):
        """MessageSendParams를 받아서 Task/Message 반환"""
        message = params.get("message")
        # 처리 로직
        return {"task_id": "...", "status": "completed"}
    
    async def send_message_streaming(self, params):
        """스트리밍 응답"""
        async for event in self.process_streaming(params):
            yield event
```

---

## 5. 테스트 순서

### Step 1: Kafka 실행
```bash
docker-compose up -d kafka
```

### Step 2: Data Agent 실행
```bash
python agents/data_analysis_agent.py
# 로그: "KafkaConsumerHandler started for agent: data"
```

### Step 3: CS Agent 실행
```bash
python agents/cs_feedback_agent.py
# 로그: "KafkaConsumerHandler started for agent: cs"
```

### Step 4: Balance Agent 실행
```bash
python agents/game_balance_agent.py
# 로그: "Kafka transport ready for data agent"
# 로그: "Kafka transport ready for cs agent"
```

### Step 5: 테스트
```bash
# Balance Agent가 Data Agent 호출
# Kafka를 통해 메시지 전달 확인
```

---

## 6. 디버깅 팁

### Kafka Topic 확인
```bash
# Topic 목록
kafka-topics --list --bootstrap-server localhost:9092

# 메시지 확인
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic agent.data.requests --from-beginning
```

### 로그 확인
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 7. 주의사항

⚠️ **MessageSendParams 직렬화**
- Kafka는 JSON으로 직렬화
- Pydantic 모델은 `.dict()` 또는 `.model_dump()` 필요

⚠️ **Executor 인터페이스**
- KafkaConsumerHandler가 기대하는 메서드 구현 필요
- 기존 A2A Executor와 다를 수 있음

⚠️ **에러 처리**
- Kafka 연결 실패 시 재시도 로직 필요
- Dead Letter Queue 고려

---

## 다음 단계

1. ✅ Balance Agent 수정
2. ✅ Data Agent 수정
3. ✅ CS Agent 수정
4. ✅ 통합 테스트
5. ⚠️ Executor 인터페이스 확인
6. ⚠️ 에러 처리 강화
