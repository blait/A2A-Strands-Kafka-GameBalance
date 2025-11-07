# 멀티턴 대화와 Correlation ID

## 정답: 새로 생성됩니다! ✅

**각 요청마다 새로운 Correlation ID가 생성됩니다.**

하지만 **context_id**로 대화를 연결합니다.

---

## 핵심 개념

### Correlation ID
- **목적**: 요청-응답 매칭
- **범위**: 단일 요청-응답
- **생명주기**: 요청 시작 ~ 응답 완료
- **매번 새로 생성**

### Context ID
- **목적**: 대화 연결
- **범위**: 전체 대화 세션
- **생명주기**: 대화 시작 ~ 대화 종료
- **계속 유지**

---

## 멀티턴 대화 흐름

### 시나리오: "승률 알려줘" → "테란" → "저그는?"

#### 1번째 요청

```python
# Client
correlation_id_1 = "abc-123"  # 새로 생성
context_id = "ctx-001"        # 새로 생성

await producer.send(
    "agent.data.requests",
    key="abc-123",  # Correlation ID
    value={
        "method": "send_message_streaming",
        "params": {
            "message": {"text": "승률 알려줘"},
            "context_id": "ctx-001"  # Context ID
        }
    }
)
```

**응답:**
```python
Task(
    task_id="task-1",
    status="input_required",  # 추가 정보 필요
    context_id="ctx-001"
)
```

#### 2번째 요청 (추가 정보 제공)

```python
# Client
correlation_id_2 = "def-456"  # 새로 생성! (다름)
context_id = "ctx-001"        # 동일! (같음)

await producer.send(
    "agent.data.requests",
    key="def-456",  # 새로운 Correlation ID
    value={
        "method": "send_message_streaming",
        "params": {
            "message": {"text": "테란"},
            "context_id": "ctx-001"  # 같은 Context ID
        }
    }
)
```

**응답:**
```python
Task(
    task_id="task-2",
    status="completed",
    context_id="ctx-001",  # 같은 Context
    result="테란 승률 58%"
)
```

#### 3번째 요청 (추가 질문)

```python
# Client
correlation_id_3 = "ghi-789"  # 또 새로 생성!
context_id = "ctx-001"        # 여전히 동일!

await producer.send(
    "agent.data.requests",
    key="ghi-789",  # 또 다른 Correlation ID
    value={
        "method": "send_message_streaming",
        "params": {
            "message": {"text": "저그는?"},
            "context_id": "ctx-001"  # 같은 Context ID
        }
    }
)
```

---

## 코드로 확인

### Client-side (Balance Agent)

```python
# gui/balance_gui.py
class BalanceGUI:
    def __init__(self):
        self.context_id = None  # Context ID 저장
    
    async def send_message(self, user_input):
        # Context ID 생성 (첫 요청 시)
        if self.context_id is None:
            self.context_id = str(uuid4())  # "ctx-001"
        
        # 메시지 생성
        msg = Message(
            role=Role.user,
            parts=[TextPart(text=user_input)],
            message_id=uuid4().hex,
            context_id=self.context_id  # Context ID 포함
        )
        
        # Transport 호출 (Correlation ID는 내부에서 생성)
        async for event in self.transport.send_message_streaming(
            MessageSendParams(message=msg)
        ):
            yield event
```

### KafkaTransport

```python
# kafka/kafka_transport.py
class KafkaTransport:
    async def send_message_streaming(self, request):
        # Correlation ID 생성 (매번 새로 생성!)
        correlation_id = str(uuid4())  # "abc-123", "def-456", "ghi-789"...
        
        # Response Queue 생성
        response_queue = asyncio.Queue()
        self._pending_responses[correlation_id] = response_queue
        
        # Kafka로 발행
        await self.producer.send(
            f"agent.{self.target_agent_name}.requests",
            key=correlation_id.encode(),  # 새로운 Correlation ID
            value={
                "method": "send_message_streaming",
                "params": {
                    "message": request.message.model_dump()  # Context ID 포함
                }
            }
        )
        
        # 응답 대기
        while True:
            response = await response_queue.get()
            if response.get("final"):
                break
            yield response
```

---

## 왜 Correlation ID를 새로 생성하나?

### 이유 1: 요청-응답 매칭

각 요청은 독립적인 Kafka 메시지:
```
요청 1: key="abc-123" → 응답 1: key="abc-123"
요청 2: key="def-456" → 응답 2: key="def-456"
요청 3: key="ghi-789" → 응답 3: key="ghi-789"
```

### 이유 2: 동시 요청 처리

```python
# 동시에 여러 요청 가능
task1 = transport.send_message("승률?")      # correlation_id="abc-123"
task2 = transport.send_message("밸런스?")    # correlation_id="def-456"

# 각각 독립적으로 응답 수신
response1 = await task1  # "abc-123" 응답
response2 = await task2  # "def-456" 응답
```

### 이유 3: Kafka 메시지 특성

Kafka는 메시지 단위로 처리:
- 각 메시지는 독립적
- Key로 파티션 결정
- 순서 보장은 같은 Key 내에서만

---

## Context ID로 대화 연결

### Server-side에서 Context 관리

```python
# agents/data_analysis_agent_executor.py
class DataAnalysisExecutor:
    def __init__(self):
        self.conversation_history = {}  # context_id → 대화 기록
    
    async def execute(self, context: RequestContext, event_queue):
        context_id = context.context_id
        
        # 이전 대화 기록 조회
        history = self.conversation_history.get(context_id, [])
        
        # 현재 메시지 추가
        history.append(context.message)
        
        # 대화 기록 기반으로 처리
        if len(history) == 1:
            # 첫 요청: "승률 알려줘"
            result = "어떤 종족의 승률을 알려드릴까요?"
            status = "input_required"
        elif len(history) == 2:
            # 두 번째 요청: "테란"
            result = "테란 승률 58%"
            status = "completed"
        
        # 대화 기록 저장
        self.conversation_history[context_id] = history
        
        # 이벤트 발행
        await event_queue.enqueue_event(...)
```

---

## 전체 흐름 (멀티턴)

```
1번째 요청
───────────────────────────────────────────────────
Client:
  correlation_id: "abc-123" (새로 생성)
  context_id: "ctx-001" (새로 생성)
  message: "승률 알려줘"

Server:
  context_id: "ctx-001" 확인
  history: ["승률 알려줘"]
  response: "어떤 종족?"
  status: "input_required"

Client:
  correlation_id: "abc-123" 응답 수신
  Response Queue 삭제


2번째 요청
───────────────────────────────────────────────────
Client:
  correlation_id: "def-456" (새로 생성!)
  context_id: "ctx-001" (동일!)
  message: "테란"

Server:
  context_id: "ctx-001" 확인
  history: ["승률 알려줘", "테란"]  ← 이전 대화 기억
  response: "테란 승률 58%"
  status: "completed"

Client:
  correlation_id: "def-456" 응답 수신
  Response Queue 삭제


3번째 요청
───────────────────────────────────────────────────
Client:
  correlation_id: "ghi-789" (또 새로 생성!)
  context_id: "ctx-001" (여전히 동일!)
  message: "저그는?"

Server:
  context_id: "ctx-001" 확인
  history: ["승률 알려줘", "테란", "저그는?"]
  response: "저그 승률 42%"
  status: "completed"

Client:
  correlation_id: "ghi-789" 응답 수신
  Response Queue 삭제
```

---

## Correlation ID vs Context ID

| 항목 | Correlation ID | Context ID |
|------|---------------|-----------|
| **목적** | 요청-응답 매칭 | 대화 연결 |
| **범위** | 단일 요청-응답 | 전체 대화 |
| **생성** | 매 요청마다 | 대화 시작 시 |
| **생명주기** | 요청~응답 | 대화 시작~종료 |
| **위치** | Kafka Key | Message 내부 |
| **관리** | KafkaTransport | GUI/Client |
| **예시** | "abc-123", "def-456" | "ctx-001" |

---

## 실제 Kafka 메시지

### 1번째 요청

```
Topic: agent.data.requests
Key: "abc-123"  ← Correlation ID (새로 생성)
Value: {
  "method": "send_message_streaming",
  "params": {
    "message": {
      "text": "승률 알려줘",
      "context_id": "ctx-001"  ← Context ID (새로 생성)
    }
  }
}
```

### 2번째 요청

```
Topic: agent.data.requests
Key: "def-456"  ← Correlation ID (새로 생성!)
Value: {
  "method": "send_message_streaming",
  "params": {
    "message": {
      "text": "테란",
      "context_id": "ctx-001"  ← Context ID (동일!)
    }
  }
}
```

---

## GUI에서 Context ID 관리

```python
# gui/balance_gui.py
class BalanceGUI:
    def __init__(self):
        self.context_id = None
        self.conversation_history = []
    
    def new_conversation(self):
        """새 대화 시작"""
        self.context_id = str(uuid4())
        self.conversation_history = []
    
    async def send_message(self, user_input):
        # 첫 메시지면 Context ID 생성
        if self.context_id is None:
            self.context_id = str(uuid4())
        
        # 메시지 생성 (Context ID 포함)
        msg = Message(
            text=user_input,
            context_id=self.context_id  # 같은 Context ID
        )
        
        # Transport 호출 (Correlation ID는 자동 생성)
        async for event in self.transport.send_message_streaming(msg):
            yield event
        
        # 대화 기록 저장
        self.conversation_history.append({
            "user": user_input,
            "assistant": response
        })
```

---

## 정리

### Correlation ID
- ✅ 매 요청마다 새로 생성
- ✅ 요청-응답 매칭용
- ✅ Kafka Key로 사용
- ✅ 응답 완료 시 삭제

### Context ID
- ✅ 대화 시작 시 생성
- ✅ 대화 연결용
- ✅ Message 내부에 포함
- ✅ 대화 종료까지 유지

### 멀티턴 대화

```
요청 1: correlation_id="abc-123", context_id="ctx-001"
요청 2: correlation_id="def-456", context_id="ctx-001"  ← 새 Correlation, 같은 Context
요청 3: correlation_id="ghi-789", context_id="ctx-001"  ← 새 Correlation, 같은 Context
```

**핵심:**
- Correlation ID = 요청마다 새로 생성
- Context ID = 대화 전체에서 유지
- 둘의 조합으로 멀티턴 대화 구현!
