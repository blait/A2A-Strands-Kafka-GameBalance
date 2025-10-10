# Task 관리 - HTTP vs Kafka

## Task란?

A2A 프로토콜에서 **비동기 작업의 상태를 추적**하는 객체

```python
Task {
    task_id: "abc-123",
    status: "completed",
    artifacts: [...],  # 결과물
    events: [...]      # 진행 이벤트
}
```

---

## 현재 HTTP 방식의 Task 관리

### 구조

```
HTTP POST /v1/message:send
    ↓
A2AStarletteApplication
    ↓
DefaultRequestHandler
    ↓
1. Task 생성 (TaskStore)
2. AgentExecutor.execute(context, event_queue)
3. Task 업데이트 (이벤트 수집)
4. Task 반환
```

### 코드

```python
# data_analysis_agent.py

# 1. RequestHandler 생성
request_handler = DefaultRequestHandler(
    agent_executor=DataAnalysisExecutor(),
    task_store=InMemoryTaskStore()
)

# 2. A2A 서버에 연결
a2a_server = A2AStarletteApplication(
    request_handler=request_handler,
    agent_card=agent_card
)

# 3. HTTP 서버 실행
uvicorn.run(app, host="0.0.0.0", port=9003)
```

### DefaultRequestHandler의 역할

```python
class DefaultRequestHandler:
    def __init__(self, agent_executor, task_store):
        self.agent_executor = agent_executor
        self.task_store = task_store
    
    async def send_message(self, params):
        # 1. Task 생성
        task = await self.task_store.create_task(
            task_id=uuid4(),
            message=params.message
        )
        
        # 2. EventQueue 생성
        event_queue = EventQueue()
        
        # 3. RequestContext 생성
        context = RequestContext(
            task_id=task.task_id,
            message=params.message,
            current_task=task
        )
        
        # 4. Executor 실행
        await self.agent_executor.execute(context, event_queue)
        
        # 5. 이벤트 수집 및 Task 업데이트
        events = await event_queue.get_all_events()
        for event in events:
            await self.task_store.add_event(task.task_id, event)
        
        # 6. 최종 Task 반환
        return await self.task_store.get_task(task.task_id)
```

---

## Kafka 방식의 Task 관리

### 핵심: DefaultRequestHandler 재사용!

```
Kafka Message
    ↓
KafkaConsumerHandler
    ↓
DefaultRequestHandler.send_message()  ← 재사용!
    ↓
1. Task 생성
2. Executor 실행
3. Task 업데이트
4. Task 반환 (Kafka로)
```

### 코드

```python
# kafka/kafka_consumer_handler.py

class KafkaConsumerHandler:
    def __init__(self, agent_name, agent_executor, task_store=None):
        self.agent_name = agent_name
        
        # DefaultRequestHandler 재사용!
        self.request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=task_store or InMemoryTaskStore()
        )
        
        self.consumer = None
        self.producer = None
    
    async def _handle_request(self, msg):
        correlation_id = msg.key.decode()
        request = msg.value
        
        # DefaultRequestHandler에게 위임
        result = await self.request_handler.send_message(
            MessageSendParams(**request["params"])
        )
        
        # Kafka로 응답 전송
        await self.producer.send(
            f"agent.{self.agent_name}.responses",
            key=correlation_id.encode(),
            value=result.model_dump()
        )
```

### 사용 예시

```python
# data_analysis_agent.py

# HTTP 서버 (기존)
request_handler = DefaultRequestHandler(
    agent_executor=DataAnalysisExecutor(),
    task_store=InMemoryTaskStore()
)
a2a_server = A2AStarletteApplication(request_handler=request_handler)

# Kafka Consumer (추가)
kafka_handler = KafkaConsumerHandler(
    agent_name="data",
    agent_executor=DataAnalysisExecutor(),  # 같은 Executor
    task_store=InMemoryTaskStore()          # 같은 TaskStore
)
await kafka_handler.start()
```

---

## Task 관리 비교

| 항목 | HTTP | Kafka |
|------|------|-------|
| **Task 생성** | DefaultRequestHandler | DefaultRequestHandler (재사용) |
| **Task 저장** | InMemoryTaskStore | InMemoryTaskStore (동일) |
| **Executor** | DataAnalysisExecutor | DataAnalysisExecutor (동일) |
| **이벤트 수집** | EventQueue | EventQueue (동일) |
| **Task 업데이트** | 자동 | 자동 (동일) |
| **코드 수정** | 불필요 | 불필요 |

---

## 왜 Task 코드 수정이 불필요한가?

### 1. DefaultRequestHandler가 모든 Task 관리 담당

```python
# HTTP든 Kafka든 동일하게 호출
await request_handler.send_message(params)
```

### 2. Transport 계층과 Task 관리는 독립적

```
┌─────────────────────────────────────┐
│  Transport Layer (HTTP/Kafka)       │  ← 변경됨
├─────────────────────────────────────┤
│  DefaultRequestHandler              │  ← 그대로
│  - Task 생성                        │
│  - Executor 실행                    │
│  - Task 업데이트                    │
├─────────────────────────────────────┤
│  AgentExecutor                      │  ← 그대로
│  TaskStore                          │  ← 그대로
└─────────────────────────────────────┘
```

### 3. 같은 인터페이스 사용

```python
# HTTP
result = await request_handler.send_message(params)

# Kafka
result = await request_handler.send_message(params)
# ↑ 똑같음!
```

---

## Task 상태 흐름

### 1. Task 생성
```python
task = Task(
    task_id="abc-123",
    status=TaskStatus(state=TaskState.working),
    artifacts=[]
)
```

### 2. Executor 실행 중
```python
# Thinking 이벤트
TaskArtifactUpdateEvent(
    artifact=Artifact(parts=[TextPart(text="🧠 분석 중...")])
)

# 상태 업데이트
TaskStatusUpdateEvent(
    status=TaskStatus(state=TaskState.working)
)
```

### 3. Task 완료
```python
# 최종 결과
TaskArtifactUpdateEvent(
    artifact=Artifact(parts=[TextPart(text="테란 승률 58%")])
)

# 완료 상태
TaskStatusUpdateEvent(
    status=TaskStatus(state=TaskState.completed),
    final=True
)
```

### 4. Task 조회
```python
task = await task_store.get_task("abc-123")
# {
#   task_id: "abc-123",
#   status: "completed",
#   artifacts: [...]
# }
```

---

## 멀티턴 대화와 Task

### HTTP 방식
```python
# 1번째 요청
POST /v1/message:send
Body: {"message": {"text": "승률 알려줘"}}
Response: Task(task_id="task-1", status="input_required")

# 2번째 요청 (같은 context)
POST /v1/message:send
Body: {
    "message": {"text": "테란"},
    "context_id": "ctx-1"  # 이전 대화 연결
}
Response: Task(task_id="task-2", status="completed")
```

### Kafka 방식 (동일)
```python
# 1번째 요청
Kafka: agent.data.requests
Key: "corr-1"
Value: {"message": {"text": "승률 알려줘"}}
Response: Task(task_id="task-1", status="input_required")

# 2번째 요청
Kafka: agent.data.requests
Key: "corr-2"
Value: {
    "message": {"text": "테란"},
    "context_id": "ctx-1"  # 이전 대화 연결
}
Response: Task(task_id="task-2", status="completed")
```

**멀티턴도 동일하게 작동!**

---

## TaskStore 종류

### InMemoryTaskStore (현재 사용)
```python
task_store = InMemoryTaskStore()
# 메모리에만 저장
# 재시작 시 손실
```

### 프로덕션 옵션
```python
# Redis
task_store = RedisTaskStore(redis_client)

# DynamoDB
task_store = DynamoDBTaskStore(table_name)

# PostgreSQL
task_store = PostgreSQLTaskStore(connection)
```

**Kafka 방식에서도 동일하게 교체 가능!**

---

## 결론

### Task 관리 코드 수정 불필요 ✅

**이유:**
1. DefaultRequestHandler가 모든 Task 관리 담당
2. HTTP/Kafka 모두 동일한 인터페이스 사용
3. Transport 계층과 Task 관리는 독립적

### 수정 필요한 것

❌ Task 관리 로직
❌ AgentExecutor
❌ TaskStore
❌ EventQueue

✅ KafkaConsumerHandler (새로 작성)
✅ Balance Agent (Transport 교체)

**Task는 그대로, Transport만 바꾸면 끝!**
