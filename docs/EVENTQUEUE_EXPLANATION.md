# EventQueue - A2A SDK가 제공하는 이벤트 관리 시스템

## 정답 ✅

**EventQueue는 A2A SDK가 원래 제공하는 것입니다. 우리가 만든 게 아닙니다!**

**위치**: `a2a/server/events/event_queue.py` (A2A SDK 내부)

---

## EventQueue란?

### 역할

AgentExecutor가 발행한 이벤트를 수집하고 전달하는 큐

```python
# a2a/server/events/event_queue.py (A2A SDK)
class EventQueue:
    """이벤트를 수집하고 스트리밍하는 큐"""
    
    def __init__(self):
        self._queue = asyncio.Queue()
    
    async def enqueue_event(self, event):
        """이벤트 추가"""
        await self._queue.put(event)
    
    async def stream(self):
        """이벤트 스트리밍"""
        while True:
            event = await self._queue.get()
            yield event
```

---

## 사용 흐름

### 1. DefaultRequestHandler가 EventQueue 생성

```python
# a2a/server/request_handlers.py (A2A SDK)
class DefaultRequestHandler:
    async def on_message_send_stream(self, params):
        # 1. EventQueue 생성 (SDK가 자동으로)
        event_queue = EventQueue()
        
        # 2. RequestContext 생성
        context = RequestContext(
            task_id=task.task_id,
            message=params.message
        )
        
        # 3. AgentExecutor에게 EventQueue 전달
        await self.agent_executor.execute(context, event_queue)
        
        # 4. EventQueue에서 이벤트 수신
        async for event in event_queue.stream():
            yield event
```

### 2. AgentExecutor가 EventQueue에 이벤트 발행

```python
# agents/data_analysis_agent_executor.py (우리가 작성)
class DataAnalysisExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """
        event_queue는 DefaultRequestHandler가 전달해줌
        우리는 이벤트를 발행만 하면 됨
        """
        
        # 작업 수행
        result = await self.analyze_data(context.message)
        
        # 이벤트 발행 (EventQueue에 추가)
        await event_queue.enqueue_event(TaskArtifactUpdateEvent(
            taskId=context.task_id,
            artifact=Artifact(parts=[TextPart(text=result)])
        ))
        
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            taskId=context.task_id,
            status=TaskStatus(state=TaskState.completed),
            final=True
        ))
```

### 3. DefaultRequestHandler가 EventQueue에서 이벤트 수신

```python
# DefaultRequestHandler (SDK)
async for event in event_queue.stream():
    # 이벤트를 받아서 yield
    yield event
```

---

## 전체 흐름

```
DefaultRequestHandler (SDK)
    |
    | 1. EventQueue 생성
    |
    ↓
EventQueue (SDK)
    |
    | 2. EventQueue 전달
    |
    ↓
AgentExecutor (우리가 작성)
    |
    | 3. enqueue_event() 호출
    |
    ↓
EventQueue (SDK)
    |
    | 4. stream() 호출
    |
    ↓
DefaultRequestHandler (SDK)
    |
    | 5. yield event
    |
    ↓
KafkaConsumerHandler (우리가 작성)
    |
    | 6. Kafka로 전송
    |
    ↓
Kafka
```

---

## 우리가 작성한 것 vs SDK가 제공한 것

### A2A SDK가 제공 (우리가 만들지 않음)

```python
# a2a/server/events/event_queue.py
class EventQueue:
    """SDK가 제공"""
    
    async def enqueue_event(self, event):
        """이벤트 추가"""
        await self._queue.put(event)
    
    async def stream(self):
        """이벤트 스트리밍"""
        while True:
            event = await self._queue.get()
            yield event
```

**SDK가 제공하는 것:**
- ✅ EventQueue 클래스
- ✅ enqueue_event() 메서드
- ✅ stream() 메서드
- ✅ 내부 Queue 관리

### 우리가 작성한 것

```python
# agents/data_analysis_agent_executor.py
class DataAnalysisExecutor(AgentExecutor):
    async def execute(self, context, event_queue):
        """우리가 작성"""
        
        # EventQueue 사용 (SDK가 제공한 것)
        await event_queue.enqueue_event(event)
```

**우리가 작성한 것:**
- ✅ AgentExecutor 구현
- ✅ enqueue_event() 호출 (사용만)
- ❌ EventQueue 구현 (SDK가 제공)

---

## 코드 예시

### AgentExecutor에서 EventQueue 사용

```python
# agents/game_balance_agent_executor.py
class GameBalanceExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """
        event_queue는 파라미터로 받음 (SDK가 전달)
        우리는 사용만 하면 됨
        """
        
        try:
            # 1. 작업 수행
            result = await agent.invoke_async(input_text)
            
            # 2. Artifact 이벤트 발행
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                artifact=Artifact(
                    artifactId=f"response-{context.task_id}",
                    parts=[TextPart(text=result)]
                )
            ))
            
            # 3. Status 이벤트 발행
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                status=TaskStatus(state='completed'),
                final=True
            ))
            
        except Exception as e:
            # 4. 에러 이벤트 발행
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                status=TaskStatus(state='failed'),
                final=True
            ))
```

**우리가 하는 일:**
- `event_queue.enqueue_event()` 호출만
- EventQueue 내부 구현은 신경 쓰지 않음

---

## EventQueue의 내부 동작 (참고)

### 실제 구현 (A2A SDK)

```python
# a2a/server/events/event_queue.py (SDK 내부)
class EventQueue:
    def __init__(self):
        self._queue = asyncio.Queue()  # asyncio Queue 사용
        self._closed = False
    
    async def enqueue_event(self, event: Event):
        """이벤트 추가"""
        if self._closed:
            raise RuntimeError("EventQueue is closed")
        await self._queue.put(event)
    
    async def stream(self) -> AsyncGenerator[Event, None]:
        """이벤트 스트리밍"""
        while not self._closed:
            try:
                event = await self._queue.get()
                yield event
                
                # final 이벤트면 종료
                if hasattr(event, 'final') and event.final:
                    self._closed = True
                    break
            except asyncio.CancelledError:
                break
    
    def close(self):
        """큐 닫기"""
        self._closed = True
```

**핵심:**
- `asyncio.Queue` 기반
- `enqueue_event()`로 추가
- `stream()`으로 수신
- `final=True` 이벤트로 종료

---

## 왜 EventQueue를 사용하나?

### 문제: 비동기 이벤트 전달

AgentExecutor는 여러 개의 이벤트를 순차적으로 발행해야 함:
1. Thinking 이벤트
2. 중간 결과 이벤트
3. 최종 결과 이벤트
4. 상태 업데이트 이벤트

### 해결: EventQueue

```python
# AgentExecutor
await event_queue.enqueue_event(event1)  # 추가
await event_queue.enqueue_event(event2)  # 추가
await event_queue.enqueue_event(event3)  # 추가

# DefaultRequestHandler
async for event in event_queue.stream():  # 순차적으로 수신
    yield event
```

**장점:**
- 비동기 이벤트 전달
- 순서 보장
- 백프레셔 처리 (Queue가 가득 차면 대기)

---

## HTTP vs Kafka 모두 동일

### HTTP 방식

```python
# HTTP 서버
app = A2AStarletteApplication(
    request_handler=DefaultRequestHandler(...)
)

# DefaultRequestHandler 내부
event_queue = EventQueue()  # ← 동일!
await executor.execute(context, event_queue)
async for event in event_queue.stream():
    yield event  # → HTTP SSE로 전송
```

### Kafka 방식

```python
# Kafka Consumer
handler = KafkaConsumerHandler(...)

# DefaultRequestHandler 내부
event_queue = EventQueue()  # ← 동일!
await executor.execute(context, event_queue)
async for event in event_queue.stream():
    yield event  # → Kafka로 전송
```

**핵심:**
- EventQueue는 HTTP/Kafka 관계없이 동일
- Transport만 다름 (HTTP SSE vs Kafka)

---

## 정리

### EventQueue는 A2A SDK가 제공 ✅

**위치**: `a2a/server/events/event_queue.py`

**제공하는 것:**
- EventQueue 클래스
- enqueue_event() 메서드
- stream() 메서드

**우리가 하는 일:**
- enqueue_event() 호출만
- EventQueue 구현은 SDK가 담당

### 역할 분담

```
┌──────────────────────────────────────┐
│  A2A SDK가 제공                       │
│  - EventQueue                        │
│  - DefaultRequestHandler             │
│  - TaskStore                         │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  우리가 작성                          │
│  - KafkaConsumerHandler              │
│  - AgentExecutor                     │
│  - event_queue.enqueue_event() 호출  │
└──────────────────────────────────────┘
```

### 핵심

- EventQueue = A2A SDK가 제공하는 이벤트 관리 시스템
- 우리는 사용만 함 (enqueue_event 호출)
- HTTP든 Kafka든 동일하게 사용
- 비동기 이벤트 전달의 핵심 컴포넌트
