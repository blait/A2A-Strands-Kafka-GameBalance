# Kafka Transport 로직 상세 설명

## 개요

KafkaTransport는 A2A 프로토콜의 `ClientTransport` 인터페이스를 구현하여 HTTP 대신 Kafka를 통해 에이전트 간 통신을 가능하게 합니다.

**핵심 아이디어:**
- Producer: 요청 발행
- Consumer: 응답 수신 (백그라운드)
- Correlation ID: 요청-응답 매칭
- Queue: 비동기 응답 전달

---

## 전체 구조

```
Balance Agent (Client)
    │
    ├─ KafkaTransport
    │   ├─ Producer (요청 발행)
    │   ├─ Consumer (응답 수신, 백그라운드)
    │   └─ Pending Responses (correlation_id → Queue)
    │
    ↓ Kafka
    │
Data Agent (Server)
    │
    └─ KafkaConsumerHandler
        ├─ Consumer (요청 수신)
        ├─ DefaultRequestHandler (처리)
        └─ Producer (응답 발행)
```

---

## 1. 초기화 (Startup)

### KafkaTransport 생성

```python
# Balance Agent에서 Transport 생성
transport = KafkaTransport(
    target_agent_name="data",  # 대상 Agent
    bootstrap_servers="localhost:9092"
)
```

### Producer/Consumer 시작

```python
async def _ensure_started(self):
    """Kafka Producer와 Consumer 시작"""
    
    # 1. Producer 시작 (요청 발행용)
    if self.producer is None:
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode()
        )
        await self.producer.start()
        print(f"✅ Producer started for {self.target_agent_name}")
    
    # 2. Consumer 시작 (응답 수신용)
    if self.consumer is None:
        self.consumer = AIOKafkaConsumer(
            f"agent.{self.target_agent_name}.responses",  # 응답 topic
            bootstrap_servers=self.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode()),
            group_id=f"client-{uuid4().hex[:8]}"  # 고유 Group ID
        )
        await self.consumer.start()
        
        # 3. 백그라운드 Consumer Task 시작
        self._consumer_task = asyncio.create_task(self._consume_responses())
        print(f"✅ Consumer started for {self.target_agent_name}")
```

**핵심:**
- Producer: 즉시 시작
- Consumer: 백그라운드 Task로 실행
- Group ID: 각 Client마다 고유 (응답 중복 수신 방지)

---

## 2. 메시지 전송 (send_message_streaming)

### 2.1 요청 준비

```python
async def send_message_streaming(self, request, context=None):
    """스트리밍 메시지 전송"""
    
    # 1. Producer/Consumer 시작 확인
    await self._ensure_started()
    
    # 2. Correlation ID 생성 (요청-응답 매칭용)
    correlation_id = str(uuid4())  # "abc-123-def-456"
    
    # 3. 응답 Queue 생성
    response_queue = asyncio.Queue()
    self._pending_responses[correlation_id] = response_queue
    
    print(f"📤 [Transport] Created request: {correlation_id}")
```

**Correlation ID:**
- 각 요청마다 고유 UUID 생성
- Kafka 메시지의 Key로 사용
- 응답 매칭에 사용

**Pending Responses:**
```python
self._pending_responses = {
    "abc-123": Queue(),  # 요청 1의 응답 Queue
    "def-456": Queue(),  # 요청 2의 응답 Queue
}
```

### 2.2 Kafka로 요청 발행

```python
    # 4. 요청 메시지 생성
    payload = {
        "method": "send_message_streaming",
        "params": {
            "message": request.message.model_dump()
        }
    }
    
    # 5. Kafka Producer로 발행
    await self.producer.send(
        f"agent.{self.target_agent_name}.requests",  # Topic
        key=correlation_id.encode(),  # Key: Correlation ID
        value=payload  # Value: 요청 내용
    )
    
    print(f"✅ [Transport] Request sent to agent.data.requests")
```

**Kafka 메시지:**
```
Topic: agent.data.requests
Key: "abc-123-def-456"
Value: {
  "method": "send_message_streaming",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"text": "테란 승률?"}]
    }
  }
}
```

### 2.3 응답 수신 (Streaming)

```python
    # 6. 응답 Queue에서 이벤트 수신
    try:
        while True:
            # Queue에서 응답 대기
            response = await response_queue.get()
            
            print(f"📦 [Transport] Got response: {response.get('type')}")
            
            # 에러 체크
            if response.get("error"):
                raise Exception(f"Agent error: {response['error']}")
            
            # 종료 신호 체크
            if response.get("final"):
                print(f"🏁 [Transport] Stream completed")
                break
            
            # 이벤트 타입에 따라 객체 생성
            event_type = response.get("type")
            
            if event_type == "Task":
                yield Task(**response)
            elif event_type == "Message":
                yield Message(**response)
            elif event_type == "TaskStatusUpdateEvent":
                yield TaskStatusUpdateEvent(**response)
            elif event_type == "TaskArtifactUpdateEvent":
                yield TaskArtifactUpdateEvent(**response)
    
    finally:
        # 7. 정리
        if correlation_id in self._pending_responses:
            del self._pending_responses[correlation_id]
```

**응답 흐름:**
```
1. response_queue.get() 호출 (블로킹)
2. 백그라운드 Consumer가 응답을 Queue에 넣음
3. get()이 응답을 반환
4. 이벤트 타입에 따라 객체 생성
5. yield로 호출자에게 전달
6. final=true까지 반복
```

---

## 3. 백그라운드 응답 수신 (_consume_responses)

### 3.1 Consumer Loop

```python
async def _consume_responses(self):
    """백그라운드에서 계속 응답 수신"""
    
    try:
        # Kafka Consumer에서 메시지 수신 (무한 루프)
        async for msg in self.consumer:
            # 1. Correlation ID 추출
            correlation_id = msg.key.decode()
            
            print(f"📨 [Transport] Received response for {correlation_id}")
            
            # 2. 해당 요청의 Queue 찾기
            if correlation_id in self._pending_responses:
                # 3. Queue에 응답 넣기
                await self._pending_responses[correlation_id].put(msg.value)
                print(f"✅ [Transport] Put response in queue")
            else:
                print(f"⚠️ [Transport] No pending request for {correlation_id}")
    
    except Exception as e:
        print(f"❌ [Transport] Error in consumer: {e}")
```

**핵심 동작:**
1. **무한 루프**: `async for msg in self.consumer`로 계속 수신
2. **Key 확인**: Correlation ID 추출
3. **Queue 찾기**: `_pending_responses`에서 해당 Queue 찾기
4. **응답 전달**: Queue에 put하여 요청자에게 전달

### 3.2 Correlation ID 매칭

```
요청 시:
  correlation_id = "abc-123"
  _pending_responses["abc-123"] = Queue()

응답 수신 시:
  msg.key = "abc-123"
  queue = _pending_responses["abc-123"]
  queue.put(msg.value)

요청자:
  response = await queue.get()  ← 여기서 응답 받음
```

---

## 4. Server-Side: KafkaConsumerHandler

### 4.1 요청 수신

```python
class KafkaConsumerHandler:
    async def start(self):
        """Kafka 요청 수신 시작"""
        
        # 1. Consumer 시작 (요청 수신용)
        self.consumer = AIOKafkaConsumer(
            f"agent.{self.agent_name}.requests",  # agent.data.requests
            bootstrap_servers=self.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode())
        )
        await self.consumer.start()
        
        # 2. Producer 시작 (응답 발행용)
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode()
        )
        await self.producer.start()
        
        print(f"✅ [Handler] Ready! Listening for messages...")
        
        # 3. 메시지 처리 루프
        async for msg in self.consumer:
            print(f"📨 [Handler] Received message")
            asyncio.create_task(self._handle_request(msg))
```

### 4.2 요청 처리

```python
    async def _handle_request(self, msg):
        """요청 처리"""
        
        # 1. Correlation ID 추출
        correlation_id = msg.key.decode()
        request = msg.value
        method = request.get("method")
        params = request.get("params")
        
        print(f"📥 [Handler] method={method}, correlation_id={correlation_id}")
        
        try:
            if method == "send_message_streaming":
                # 2. DefaultRequestHandler로 처리
                message = Message(**params.get("message", {}))
                
                # 3. 스트리밍 처리
                async for event in self.request_handler.on_message_send_stream(
                    MessageSendParams(message=message)
                ):
                    # 4. 각 이벤트를 Kafka로 전송
                    event_data = event.model_dump()
                    event_data["type"] = event.__class__.__name__
                    
                    await self._send_response(
                        correlation_id, 
                        event_data, 
                        final=False
                    )
                
                # 5. 완료 신호 전송
                await self._send_response(
                    correlation_id, 
                    {"final": True}, 
                    final=True
                )
        
        except Exception as e:
            # 6. 에러 응답
            await self._send_response(
                correlation_id, 
                {"error": str(e)}, 
                final=True
            )
```

### 4.3 응답 발행

```python
    async def _send_response(self, correlation_id: str, response: dict, final: bool):
        """응답을 Kafka로 전송"""
        
        response_data = {**response, "final": final}
        
        print(f"📤 [Handler] Sending response")
        print(f"   Topic: agent.{self.agent_name}.responses")
        print(f"   Key: {correlation_id}")
        
        await self.producer.send(
            f"agent.{self.agent_name}.responses",
            key=correlation_id.encode(),  # 같은 Correlation ID 사용
            value=response_data
        )
        
        print(f"✅ [Handler] Response sent")
```

---

## 5. 전체 메시지 흐름

### 시퀀스 다이어그램

```
Balance Agent          Kafka Hub          Data Agent
(KafkaTransport)                      (KafkaConsumerHandler)
      |                    |                    |
      | 1. send_message_streaming()            |
      |                    |                    |
      | 2. correlation_id = "abc-123"          |
      | 3. Queue 생성      |                    |
      |                    |                    |
      | 4. Producer.send() |                    |
      |------------------->|                    |
      | Topic: agent.data.requests             |
      | Key: "abc-123"     |                    |
      |                    |                    |
      |                    | 5. Consumer 수신   |
      |                    |------------------->|
      |                    |                    |
      |                    |                    | 6. _handle_request()
      |                    |                    | 7. DefaultRequestHandler
      |                    |                    | 8. Event 1 생성
      |                    |                    |
      |                    | 9. Producer.send() |
      |                    |<-------------------|
      |                    | Topic: agent.data.responses
      |                    | Key: "abc-123"     |
      |                    |                    |
      | 10. Consumer 수신  |                    |
      |<-------------------|                    |
      | (백그라운드)       |                    |
      |                    |                    |
      | 11. Queue.put()    |                    |
      |                    |                    |
      | 12. Queue.get()    |                    |
      | ← Event 1          |                    |
      |                    |                    |
      | 13. yield Event 1  |                    |
      |                    |                    |
      |                    | 14. Event 2        |
      |                    |<-------------------|
      |                    |                    |
      | 15. Queue.put()    |                    |
      | 16. Queue.get()    |                    |
      | ← Event 2          |                    |
      |                    |                    |
      | 17. yield Event 2  |                    |
      |                    |                    |
      |                    | 18. final=true     |
      |                    |<-------------------|
      |                    |                    |
      | 19. Queue.put()    |                    |
      | 20. Queue.get()    |                    |
      | ← final=true       |                    |
      |                    |                    |
      | 21. break (종료)   |                    |
      |                    |                    |
```

---

## 6. 핵심 개념

### 6.1 Correlation ID

**문제:**
- Kafka는 비동기 메시징
- 여러 요청이 동시에 발생하면 응답이 섞임

**해결:**
```python
# 요청 시
correlation_id = str(uuid4())  # "abc-123"
await producer.send(
    topic="agent.data.requests",
    key=correlation_id.encode(),  # Key에 ID 저장
    value=payload
)

# 응답 시
await producer.send(
    topic="agent.data.responses",
    key=correlation_id.encode(),  # 같은 ID 사용
    value=response
)

# 수신 시
msg.key.decode()  # "abc-123"
# → 해당 요청의 Queue에 전달
```

### 6.2 비동기 응답 처리

**문제:**
- 요청 함수는 블로킹되면 안 됨
- 응답은 나중에 도착함

**해결:**
```python
# 요청 함수
async def send_message_streaming(self, request):
    # 1. Queue 생성
    queue = asyncio.Queue()
    self._pending_responses[correlation_id] = queue
    
    # 2. 요청 발행 (논블로킹)
    await self.producer.send(...)
    
    # 3. Queue에서 응답 대기 (블로킹)
    while True:
        response = await queue.get()  # 여기서 대기
        yield response

# 백그라운드 Consumer
async def _consume_responses(self):
    async for msg in self.consumer:
        # Queue에 응답 넣기 (논블로킹)
        await queue.put(msg.value)
```

### 6.3 스트리밍

**문제:**
- 여러 개의 응답을 순차적으로 전달해야 함
- 언제 끝났는지 알아야 함

**해결:**
```python
# Server: 각 이벤트마다 전송
async for event in executor.execute():
    await producer.send(
        key=correlation_id,
        value={...event..., "final": False}
    )

# 마지막 메시지
await producer.send(
    key=correlation_id,
    value={"final": True}
)

# Client: final=true까지 수신
while True:
    response = await queue.get()
    if response.get("final"):
        break
    yield response
```

### 6.4 백그라운드 Consumer

**문제:**
- 응답을 계속 수신해야 함
- 요청 함수를 블로킹하면 안 됨

**해결:**
```python
# 초기화 시 백그라운드 Task 시작
self._consumer_task = asyncio.create_task(self._consume_responses())

# 백그라운드에서 계속 실행
async def _consume_responses(self):
    async for msg in self.consumer:  # 무한 루프
        # Queue에 응답 전달
        await queue.put(msg.value)

# 종료 시 정리
async def close(self):
    self._consumer_task.cancel()
```

---

## 7. 에러 처리

### 7.1 타임아웃

```python
try:
    response = await asyncio.wait_for(
        response_queue.get(), 
        timeout=40.0  # 40초 타임아웃
    )
except asyncio.TimeoutError:
    raise Exception("Agent response timeout")
```

### 7.2 Agent 에러

```python
# Server에서 에러 발생 시
try:
    result = await executor.execute()
except Exception as e:
    await producer.send(
        key=correlation_id,
        value={"error": str(e), "final": True}
    )

# Client에서 에러 처리
response = await queue.get()
if response.get("error"):
    raise Exception(f"Agent error: {response['error']}")
```

### 7.3 연결 끊김

```python
# Consumer 재시작
try:
    async for msg in self.consumer:
        ...
except Exception as e:
    logger.error(f"Consumer error: {e}")
    # 재연결 로직
    await self.consumer.stop()
    await self.consumer.start()
```

---

## 8. 성능 최적화

### 8.1 배치 처리

```python
# Producer 설정
producer = AIOKafkaProducer(
    bootstrap_servers=...,
    linger_ms=10,  # 10ms 대기 후 배치 전송
    batch_size=16384  # 16KB 배치
)
```

### 8.2 압축

```python
producer = AIOKafkaProducer(
    compression_type='gzip'  # gzip 압축
)
```

### 8.3 병렬 처리

```python
# 여러 요청 동시 처리
tasks = [
    transport.send_message_streaming(msg1),
    transport.send_message_streaming(msg2),
    transport.send_message_streaming(msg3)
]
results = await asyncio.gather(*tasks)
```

---

## 9. 디버깅

### 9.1 로그 확인

```bash
# Transport 로그
tail -f balance_agent.log | grep Transport

# Handler 로그
tail -f data_agent.log | grep Handler
```

### 9.2 Kafka 메시지 확인

```bash
# 요청 메시지
kafka-console-consumer --topic agent.data.requests \
  --bootstrap-server localhost:9092 \
  --property print.key=true

# 응답 메시지
kafka-console-consumer --topic agent.data.responses \
  --bootstrap-server localhost:9092 \
  --property print.key=true
```

### 9.3 Correlation ID 추적

```python
# 요청 시
print(f"📤 [Transport] Request: {correlation_id}")

# 응답 수신 시
print(f"📨 [Transport] Response: {correlation_id}")

# 매칭 확인
print(f"✅ [Transport] Matched: {correlation_id}")
```

---

## 10. 코드 위치

| 컴포넌트 | 파일 | 주요 메서드 |
|---------|------|-----------|
| KafkaTransport | `kafka/kafka_transport.py` | `send_message_streaming()` |
| 백그라운드 Consumer | `kafka/kafka_transport.py` | `_consume_responses()` |
| KafkaConsumerHandler | `kafka/kafka_consumer_handler.py` | `start()`, `_handle_request()` |
| 응답 발행 | `kafka/kafka_consumer_handler.py` | `_send_response()` |

---

## 요약

### KafkaTransport의 핵심

1. **Producer**: 요청 발행
2. **Consumer**: 응답 수신 (백그라운드)
3. **Correlation ID**: 요청-응답 매칭
4. **Queue**: 비동기 응답 전달
5. **Streaming**: final 플래그로 종료 판단

### 장점

- ✅ 비동기 처리
- ✅ 스트리밍 지원
- ✅ 동시 요청 처리
- ✅ 에러 처리
- ✅ A2A 프로토콜 완전 호환

### HTTP vs Kafka

| 항목 | HTTP | Kafka |
|------|------|-------|
| 요청 | HTTP POST | Kafka Produce |
| 응답 | HTTP Response | Kafka Consume |
| 매칭 | HTTP 세션 | Correlation ID |
| 스트리밍 | SSE | Kafka 메시지 |
| 영속성 | 없음 | Kafka 로그 |
