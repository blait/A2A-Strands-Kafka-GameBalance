# Task 생성 흐름 - Task는 어디서 만들어지나?

## 요약

**Task는 `DefaultRequestHandler`에서 자동으로 생성됩니다.**

```
Kafka 요청 수신
    ↓
KafkaConsumerHandler._handle_request()
    ↓
DefaultRequestHandler.on_message_send_stream()  ← 여기서 Task 생성!
    ↓
AgentExecutor.execute()
    ↓
Task 업데이트 (이벤트 수집)
    ↓
Kafka 응답 발행
```

---

## 1. Task 생성 위치

### KafkaConsumerHandler에서 DefaultRequestHandler 호출

**파일**: `kafka/kafka_consumer_handler.py`

```python
class KafkaConsumerHandler:
    def __init__(self, agent_name, agent_executor, task_store=None):
        # DefaultRequestHandler 생성
        self.request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=task_store or InMemoryTaskStore()  # Task 저장소
        )
    
    async def _handle_request(self, msg):
        """Kafka 요청 처리"""
        correlation_id = msg.key.decode()
        request = msg.value
        method = request.get("method")
        params = request.get("params")
        
        if method == "send_message_streaming":
            message = Message(**params.get("message", {}))
            
            # DefaultRequestHandler 호출 → 여기서 Task 생성됨!
            async for event in self.request_handler.on_message_send_stream(
                MessageSendParams(message=message)
            ):
                # 생성된 Task와 이벤트를 Kafka로 전송
                event_data = event.model_dump()
                event_data["type"] = event.__class__.__name__
                await self._send_response(correlation_id, event_data, final=False)
```

**핵심:**
- `DefaultRequestHandler.on_message_send_stream()` 호출 시 Task 자동 생성
- 우리는 Task 생성 코드를 직접 작성하지 않음
- A2A SDK가 알아서 처리

---

## 2. DefaultRequestHandler 내부 동작

### Task 생성 과정 (A2A SDK 내부)

```python
# a2a/server/request_handlers.py (A2A SDK 내부)

class DefaultRequestHandler:
    def __init__(self, agent_executor, task_store):
        self.agent_executor = agent_executor
        self.task_store = task_store
    
    async def on_message_send_stream(self, params: MessageSendParams):
        """스트리밍 메시지 처리 - Task 생성"""
        
        # 1. Task 생성
        task = await self.task_store.create_task(
            task_id=str(uuid4()),
            message=params.message,
            status=TaskStatus(state=TaskState.working)
        )
        
        print(f"✅ [RequestHandler] Task created: {task.task_id}")
        
        # 2. Task 이벤트 yield
        yield task
        
        # 3. EventQueue 생성
        event_queue = EventQueue()
        
        # 4. RequestContext 생성
        context = RequestContext(
            task_id=task.task_id,
            message=params.message,
            current_task=task
        )
        
        # 5. AgentExecutor 실행
        await self.agent_executor.execute(context, event_queue)
        
        # 6. 이벤트 수집 및 전달
        async for event in event_queue.stream():
            # Task 업데이트
            if isinstance(event, TaskStatusUpdateEvent):
                task.status = event.status
            elif isinstance(event, TaskArtifactUpdateEvent):
                task.artifacts.append(event.artifact)
            
            # 이벤트 yield
            yield event
        
        # 7. 최종 Task 저장
        await self.task_store.update_task(task)
```

**Task 생성 시점:**
- `on_message_send_stream()` 호출 직후
- AgentExecutor 실행 전
- 첫 번째 yield로 Task 반환

---

## 3. Task 구조

### Task 객체

```python
Task(
    task_id="abc-123-def-456",  # UUID
    status=TaskStatus(
        state=TaskState.working  # working, completed, failed, input_required
    ),
    artifacts=[],  # 결과물 (비어있음)
    message=Message(...)  # 원본 메시지
)
```

**초기 상태:**
- `task_id`: 고유 UUID
- `status.state`: `working` (작업 중)
- `artifacts`: 빈 배열
- `message`: 사용자 요청 메시지

---

## 4. Task 업데이트 과정

### AgentExecutor에서 이벤트 발행

**파일**: `agents/data_analysis_agent_executor.py`

```python
class DataAnalysisExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """에이전트 실행"""
        
        # 1. 작업 시작
        print(f"🔧 [Executor] Starting task {context.task_id}")
        
        # 2. 비즈니스 로직 실행
        result = await self.analyze_data(context.message)
        
        # 3. Artifact 이벤트 발행
        await event_queue.enqueue_event(TaskArtifactUpdateEvent(
            taskId=context.task_id,
            contextId=context.context_id,
            artifact=Artifact(
                artifactId=f"result-{context.task_id}",
                parts=[TextPart(text=result)]
            )
        ))
        
        # 4. Status 이벤트 발행
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            taskId=context.task_id,
            contextId=context.context_id,
            status=TaskStatus(state=TaskState.completed),
            final=True
        ))
```

**이벤트 흐름:**
```
1. TaskArtifactUpdateEvent 발행
   → Task.artifacts에 추가

2. TaskStatusUpdateEvent 발행
   → Task.status 업데이트

3. DefaultRequestHandler가 이벤트 수집
   → Task 자동 업데이트
```

---

## 5. 전체 흐름 (시퀀스 다이어그램)

```
Client              Kafka              KafkaConsumerHandler    DefaultRequestHandler    AgentExecutor
  |                   |                         |                       |                      |
  | 1. send_message   |                         |                       |                      |
  |------------------>|                         |                       |                      |
  |                   |                         |                       |                      |
  |                   | 2. consume              |                       |                      |
  |                   |------------------------>|                       |                      |
  |                   |                         |                       |                      |
  |                   |                         | 3. _handle_request()  |                      |
  |                   |                         |                       |                      |
  |                   |                         | 4. on_message_send_stream()                  |
  |                   |                         |---------------------->|                      |
  |                   |                         |                       |                      |
  |                   |                         |                       | 5. create_task()     |
  |                   |                         |                       | task_id = "abc-123"  |
  |                   |                         |                       | state = working      |
  |                   |                         |                       |                      |
  |                   |                         |                       | 6. yield Task        |
  |                   |                         |<----------------------|                      |
  |                   |                         |                       |                      |
  |                   | 7. send Task            |                       |                      |
  |                   |<------------------------|                       |                      |
  |                   |                         |                       |                      |
  | 8. receive Task   |                         |                       |                      |
  |<------------------|                         |                       |                      |
  |                   |                         |                       |                      |
  |                   |                         |                       | 9. execute()         |
  |                   |                         |                       |--------------------->|
  |                   |                         |                       |                      |
  |                   |                         |                       |                      | 10. 작업 수행
  |                   |                         |                       |                      |
  |                   |                         |                       | 11. enqueue_event()  |
  |                   |                         |                       |<---------------------|
  |                   |                         |                       | (TaskArtifactUpdate) |
  |                   |                         |                       |                      |
  |                   |                         |                       | 12. yield Event      |
  |                   |                         |<----------------------|                      |
  |                   |                         |                       |                      |
  |                   | 13. send Event          |                       |                      |
  |                   |<------------------------|                       |                      |
  |                   |                         |                       |                      |
  | 14. receive Event |                         |                       |                      |
  |<------------------|                         |                       |                      |
  |                   |                         |                       |                      |
  |                   |                         |                       | 15. enqueue_event()  |
  |                   |                         |                       |<---------------------|
  |                   |                         |                       | (TaskStatusUpdate)   |
  |                   |                         |                       | state = completed    |
  |                   |                         |                       |                      |
  |                   |                         |                       | 16. yield Event      |
  |                   |                         |<----------------------|                      |
  |                   |                         |                       |                      |
  |                   | 17. send Event          |                       |                      |
  |                   |<------------------------|                       |                      |
  |                   |                         |                       |                      |
  | 18. receive Event |                         |                       |                      |
  |<------------------|                         |                       |                      |
```

---

## 6. Task 저장소 (TaskStore)

### InMemoryTaskStore

**파일**: `a2a/server/tasks.py` (A2A SDK)

```python
class InMemoryTaskStore:
    """메모리에 Task 저장"""
    
    def __init__(self):
        self.tasks = {}  # task_id → Task
    
    async def create_task(self, task_id, message, status):
        """Task 생성"""
        task = Task(
            task_id=task_id,
            message=message,
            status=status,
            artifacts=[]
        )
        self.tasks[task_id] = task
        return task
    
    async def get_task(self, task_id):
        """Task 조회"""
        return self.tasks.get(task_id)
    
    async def update_task(self, task):
        """Task 업데이트"""
        self.tasks[task.task_id] = task
```

**사용:**
```python
# KafkaConsumerHandler 생성 시
handler = KafkaConsumerHandler(
    agent_name="data",
    agent_executor=DataAnalysisExecutor(),
    task_store=InMemoryTaskStore()  # Task 저장소
)
```

---

## 7. Task 생성 코드 위치

### 실제 코드 위치

| 컴포넌트 | 파일 | 역할 |
|---------|------|------|
| **Task 생성** | `a2a/server/request_handlers.py` | DefaultRequestHandler.on_message_send_stream() |
| **Task 저장** | `a2a/server/tasks.py` | InMemoryTaskStore.create_task() |
| **Task 업데이트** | `a2a/server/request_handlers.py` | 이벤트 수집 및 Task 업데이트 |
| **Handler 호출** | `kafka/kafka_consumer_handler.py` | _handle_request() |
| **Executor 실행** | `agents/*_agent_executor.py` | execute() |

---

## 8. 우리가 작성한 코드 vs A2A SDK

### 우리가 작성한 코드

```python
# kafka/kafka_consumer_handler.py
class KafkaConsumerHandler:
    def __init__(self, agent_name, agent_executor, task_store=None):
        # DefaultRequestHandler 생성만 함
        self.request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=task_store or InMemoryTaskStore()
        )
    
    async def _handle_request(self, msg):
        # DefaultRequestHandler 호출만 함
        async for event in self.request_handler.on_message_send_stream(params):
            await self._send_response(correlation_id, event_data)
```

**우리는 Task 생성 코드를 작성하지 않음!**

### A2A SDK가 처리

```python
# a2a/server/request_handlers.py (SDK 내부)
class DefaultRequestHandler:
    async def on_message_send_stream(self, params):
        # 1. Task 생성 (SDK가 자동으로)
        task = await self.task_store.create_task(...)
        yield task
        
        # 2. Executor 실행
        await self.agent_executor.execute(context, event_queue)
        
        # 3. 이벤트 수집 및 Task 업데이트
        async for event in event_queue.stream():
            yield event
```

**A2A SDK가 자동으로 처리:**
- ✅ Task 생성
- ✅ Task 저장
- ✅ Task 업데이트
- ✅ 이벤트 수집

---

## 9. 핵심 정리

### Task는 어디서 만들어지나?

**답: `DefaultRequestHandler.on_message_send_stream()` 내부**

### 호출 체인

```
1. Kafka 요청 수신
   ↓
2. KafkaConsumerHandler._handle_request()
   ↓
3. DefaultRequestHandler.on_message_send_stream()  ← Task 생성!
   ↓
4. TaskStore.create_task()
   ↓
5. Task 객체 생성 및 저장
   ↓
6. yield Task (첫 번째 이벤트)
   ↓
7. AgentExecutor.execute()
   ↓
8. 이벤트 발행 및 Task 업데이트
```

### 우리가 할 일

- ✅ `DefaultRequestHandler` 생성
- ✅ `AgentExecutor` 구현
- ✅ 이벤트 발행 (`enqueue_event`)

### A2A SDK가 할 일

- ✅ Task 생성
- ✅ Task 저장
- ✅ Task 업데이트
- ✅ 이벤트 수집

---

## 10. 예시: Task 생성부터 완료까지

### 1. 요청 수신
```python
# Kafka 메시지
{
  "method": "send_message_streaming",
  "params": {
    "message": {"text": "테란 승률?"}
  }
}
```

### 2. Task 생성 (DefaultRequestHandler)
```python
task = Task(
    task_id="abc-123",
    status=TaskStatus(state=TaskState.working),
    artifacts=[],
    message=Message(text="테란 승률?")
)
# yield task → Kafka로 전송
```

### 3. Executor 실행
```python
# DataAnalysisExecutor.execute()
result = "테란 승률 58%"
```

### 4. Artifact 이벤트
```python
event = TaskArtifactUpdateEvent(
    taskId="abc-123",
    artifact=Artifact(parts=[TextPart(text="테란 승률 58%")])
)
# yield event → Kafka로 전송
```

### 5. Status 이벤트
```python
event = TaskStatusUpdateEvent(
    taskId="abc-123",
    status=TaskStatus(state=TaskState.completed),
    final=True
)
# yield event → Kafka로 전송
```

### 6. 최종 Task
```python
task = Task(
    task_id="abc-123",
    status=TaskStatus(state=TaskState.completed),
    artifacts=[
        Artifact(parts=[TextPart(text="테란 승률 58%")])
    ],
    message=Message(text="테란 승률?")
)
```

---

## 결론

**Task는 `DefaultRequestHandler`에서 자동으로 생성됩니다.**

- 우리는 `DefaultRequestHandler`를 생성하고 호출만 함
- A2A SDK가 Task 생성, 저장, 업데이트를 모두 처리
- HTTP든 Kafka든 동일한 로직 사용
- Transport만 바꾸면 Task 관리는 그대로!
