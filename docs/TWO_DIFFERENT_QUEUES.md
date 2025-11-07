# 두 개의 다른 Queue - EventQueue vs Response Queue

## 정답: 완전히 별개입니다! ✅

### 1. Response Queue (Correlation ID 기반)
**위치**: KafkaTransport (Client-side)
**역할**: Kafka 응답을 받아서 요청자에게 전달

### 2. EventQueue
**위치**: DefaultRequestHandler (Server-side)
**역할**: AgentExecutor의 이벤트를 수집해서 전달

---

## 1. Response Queue (Client-side)

### 위치 및 역할

**파일**: `kafka/kafka_transport.py`

```python
class KafkaTransport:
    def __init__(self):
        # Correlation ID → asyncio.Queue 매핑
        self._pending_responses = {}
    
    async def send_message_streaming(self, request):
        # 1. Correlation ID 생성
        correlation_id = str(uuid4())  # "abc-123"
        
        # 2. Response Queue 생성
        response_queue = asyncio.Queue()  # ← 이것!
        self._pending_responses[correlation_id] = response_queue
        
        # 3. Kafka로 요청 발행
        await self.producer.send(...)
        
        # 4. Response Queue에서 응답 대기
        while True:
            response = await response_queue.get()  # ← 여기서 대기
            if response.get("final"):
                break
            yield response
```

**역할:**
- Kafka에서 받은 응답을 임시 저장
- Correlation ID로 어떤 요청의 응답인지 매칭
- 요청자에게 응답 전달

**생명주기:**
- 요청 시 생성
- 응답 완료 시 삭제

---

## 2. EventQueue (Server-side)

### 위치 및 역할

**파일**: `a2a/server/events/event_queue.py` (SDK)

```python
class EventQueue:
    def __init__(self):
        self._queue = asyncio.Queue()  # ← 이것!
    
    async def enqueue_event(self, event):
        """AgentExecutor가 이벤트 추가"""
        await self._queue.put(event)
    
    async def stream(self):
        """DefaultRequestHandler가 이벤트 수신"""
        while True:
            event = await self._queue.get()
            yield event
```

**역할:**
- AgentExecutor가 발행한 이벤트를 임시 저장
- DefaultRequestHandler에게 이벤트 전달
- Kafka로 전송하기 전 단계

**생명주기:**
- DefaultRequestHandler가 생성
- Task 완료 시 종료

---

## 비교표

| 항목 | Response Queue | EventQueue |
|------|---------------|-----------|
| **위치** | KafkaTransport (Client) | DefaultRequestHandler (Server) |
| **파일** | `kafka/kafka_transport.py` | `a2a/server/events/event_queue.py` |
| **생성자** | KafkaTransport | DefaultRequestHandler |
| **사용자** | 백그라운드 Consumer → 요청자 | AgentExecutor → DefaultRequestHandler |
| **목적** | Kafka 응답 매칭 및 전달 | 이벤트 수집 및 전달 |
| **Key** | Correlation ID | 없음 |
| **개수** | 요청마다 1개 | Task마다 1개 |
| **생명주기** | 요청~응답 완료 | Task 시작~완료 |

---

## 전체 흐름에서 두 Queue의 역할

```
Balance Agent (Client)
    |
    | 1. send_message_streaming()
    |
    ↓
KafkaTransport
    |
    | 2. Response Queue 생성 (correlation_id → Queue)
    | 3. Kafka Produce
    |
    ↓
Kafka Hub
    |
    ↓
Data Agent (Server)
    |
    ↓
KafkaConsumerHandler
    |
    | 4. Kafka Consume
    |
    ↓
DefaultRequestHandler
    |
    | 5. EventQueue 생성  ← EventQueue!
    |
    ↓
AgentExecutor
    |
    | 6. event_queue.enqueue_event()  ← EventQueue 사용
    |
    ↓
EventQueue
    |
    | 7. event_queue.stream()  ← EventQueue에서 꺼냄
    |
    ↓
DefaultRequestHandler
    |
    | 8. yield event
    |
    ↓
KafkaConsumerHandler
    |
    | 9. Kafka Produce (응답)
    |
    ↓
Kafka Hub
    |
    ↓
KafkaTransport (백그라운드 Consumer)
    |
    | 10. Kafka Consume
    | 11. Response Queue.put()  ← Response Queue 사용!
    |
    ↓
Response Queue
    |
    | 12. Response Queue.get()  ← Response Queue에서 꺼냄
    |
    ↓
Balance Agent (요청자)
```

---

## 상세 코드 비교

### Response Queue (Client-side)

```python
# kafka/kafka_transport.py
class KafkaTransport:
    def __init__(self):
        # Dictionary: correlation_id → asyncio.Queue
        self._pending_responses = {
            "abc-123": Queue(),  # 요청 1
            "def-456": Queue(),  # 요청 2
        }
    
    async def send_message_streaming(self, request):
        # 요청마다 Queue 생성
        correlation_id = str(uuid4())
        response_queue = asyncio.Queue()  # ← Response Queue
        self._pending_responses[correlation_id] = response_queue
        
        # Kafka로 요청 발행
        await self.producer.send(...)
        
        # Response Queue에서 응답 대기
        while True:
            response = await response_queue.get()  # ← 여기서 대기
            yield response
    
    async def _consume_responses(self):
        """백그라운드에서 Kafka 응답 수신"""
        async for msg in self.consumer:
            correlation_id = msg.key.decode()
            
            # 해당 요청의 Response Queue에 넣기
            if correlation_id in self._pending_responses:
                queue = self._pending_responses[correlation_id]
                await queue.put(msg.value)  # ← Response Queue에 추가
```

**핵심:**
- `_pending_responses`: Correlation ID → Queue 매핑
- 백그라운드 Consumer가 `put()`
- 요청자가 `get()`

### EventQueue (Server-side)

```python
# a2a/server/request_handlers.py (SDK)
class DefaultRequestHandler:
    async def on_message_send_stream(self, params):
        # Task마다 EventQueue 생성
        event_queue = EventQueue()  # ← EventQueue
        
        # AgentExecutor 실행
        await self.agent_executor.execute(context, event_queue)
        
        # EventQueue에서 이벤트 수신
        async for event in event_queue.stream():  # ← 여기서 대기
            yield event

# agents/data_analysis_agent_executor.py (우리가 작성)
class DataAnalysisExecutor:
    async def execute(self, context, event_queue):
        # 작업 수행
        result = await self.analyze()
        
        # EventQueue에 이벤트 추가
        await event_queue.enqueue_event(event)  # ← EventQueue에 추가
```

**핵심:**
- DefaultRequestHandler가 생성
- AgentExecutor가 `enqueue_event()`
- DefaultRequestHandler가 `stream()`

---

## 실제 예시로 이해하기

### 시나리오: "테란 승률?" 요청

#### Client-side (Balance Agent)

```python
# 1. Response Queue 생성
correlation_id = "abc-123"
response_queue = asyncio.Queue()  # ← Response Queue
_pending_responses["abc-123"] = response_queue

# 2. Kafka로 요청 발행
await producer.send(
    "agent.data.requests",
    key="abc-123",
    value={"message": "테란 승률?"}
)

# 3. Response Queue에서 응답 대기
response = await response_queue.get()  # ← 블로킹
```

#### Server-side (Data Agent)

```python
# 4. Kafka 요청 수신
msg = await consumer.get()  # correlation_id = "abc-123"

# 5. EventQueue 생성
event_queue = EventQueue()  # ← EventQueue

# 6. AgentExecutor 실행
async def execute(context, event_queue):
    # 작업 수행
    result = "테란 승률 58%"
    
    # EventQueue에 이벤트 추가
    await event_queue.enqueue_event(
        TaskArtifactUpdateEvent(text=result)
    )

# 7. EventQueue에서 이벤트 수신
async for event in event_queue.stream():
    # Kafka로 응답 발행
    await producer.send(
        "agent.data.responses",
        key="abc-123",  # 같은 correlation_id
        value=event
    )
```

#### Client-side (백그라운드 Consumer)

```python
# 8. Kafka 응답 수신
msg = await consumer.get()  # key = "abc-123"

# 9. Response Queue에 넣기
queue = _pending_responses["abc-123"]
await queue.put(msg.value)  # ← Response Queue에 추가
```

#### Client-side (요청자)

```python
# 10. Response Queue에서 꺼내기
response = await response_queue.get()  # ← 여기서 받음!
print(response)  # "테란 승률 58%"
```

---

## 왜 두 개의 Queue가 필요한가?

### Response Queue가 필요한 이유

**문제:**
- Kafka는 비동기 메시징
- 여러 요청이 동시에 발생
- 응답이 섞일 수 있음

**해결:**
```python
# 요청 1
correlation_id_1 = "abc-123"
queue_1 = Queue()

# 요청 2
correlation_id_2 = "def-456"
queue_2 = Queue()

# 응답 수신 시
if msg.key == "abc-123":
    queue_1.put(response)  # 요청 1의 Queue에
elif msg.key == "def-456":
    queue_2.put(response)  # 요청 2의 Queue에
```

### EventQueue가 필요한 이유

**문제:**
- AgentExecutor는 여러 이벤트 발행
- 순차적으로 전달해야 함
- 비동기 처리 필요

**해결:**
```python
# AgentExecutor
await event_queue.enqueue_event(event1)
await event_queue.enqueue_event(event2)
await event_queue.enqueue_event(event3)

# DefaultRequestHandler
async for event in event_queue.stream():
    yield event  # 순차적으로 전달
```

---

## 정리

### Response Queue (Client-side)

**목적**: Kafka 응답을 요청자에게 전달
**위치**: KafkaTransport
**생성**: 요청 시
**사용**: 백그라운드 Consumer → 요청자
**Key**: Correlation ID

```python
# 생성
response_queue = asyncio.Queue()
_pending_responses[correlation_id] = response_queue

# 사용
await response_queue.put(response)  # Consumer
response = await response_queue.get()  # 요청자
```

### EventQueue (Server-side)

**목적**: AgentExecutor 이벤트를 수집 및 전달
**위치**: DefaultRequestHandler
**생성**: Task 시작 시
**사용**: AgentExecutor → DefaultRequestHandler
**Key**: 없음

```python
# 생성
event_queue = EventQueue()

# 사용
await event_queue.enqueue_event(event)  # AgentExecutor
async for event in event_queue.stream():  # DefaultRequestHandler
    yield event
```

### 핵심 차이

| Response Queue | EventQueue |
|---------------|-----------|
| Client-side | Server-side |
| Kafka 응답 매칭 | 이벤트 수집 |
| Correlation ID 기반 | Task 기반 |
| 요청마다 생성 | Task마다 생성 |
| 우리가 작성 | SDK가 제공 |

**완전히 별개의 Queue입니다!**
