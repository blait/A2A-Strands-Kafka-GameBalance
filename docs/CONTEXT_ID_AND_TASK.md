# Context ID와 Task의 관계

## 핵심 개념

### Context ID
- **목적**: 대화 세션 식별
- **범위**: 전체 대화
- **생명주기**: 대화 시작 ~ 종료
- **1개의 Context = 여러 개의 Task**

### Task
- **목적**: 단일 작업 추적
- **범위**: 하나의 요청-응답
- **생명주기**: 요청 시작 ~ 작업 완료
- **1개의 Task = 1개의 요청**

---

## 관계: 1 Context → N Tasks

```
Context ID: "ctx-001"
    ├─ Task 1: "task-001" (승률 알려줘)
    ├─ Task 2: "task-002" (테란)
    └─ Task 3: "task-003" (저그는?)
```

**하나의 대화(Context)에 여러 개의 작업(Task)이 포함됩니다.**

---

## 멀티턴 대화 예시

### 시나리오: "승률 알려줘" → "테란" → "저그는?"

#### 1번째 요청

```python
# Message
msg = Message(
    text="승률 알려줘",
    message_id="msg-001",
    context_id="ctx-001"  # Context ID (새로 생성)
)

# Task 생성 (DefaultRequestHandler)
task = Task(
    task_id="task-001",  # Task ID (새로 생성)
    context_id="ctx-001",  # 같은 Context ID
    status="input_required",
    message=msg
)
```

**관계:**
```
Context: ctx-001
  └─ Task: task-001 (status: input_required)
```

#### 2번째 요청 (추가 정보 제공)

```python
# Message
msg = Message(
    text="테란",
    message_id="msg-002",
    context_id="ctx-001",  # 같은 Context ID
    task_id="task-001"     # 이전 Task 참조 (선택사항)
)

# Task 생성 (DefaultRequestHandler)
task = Task(
    task_id="task-002",  # 새로운 Task ID
    context_id="ctx-001",  # 같은 Context ID
    status="completed",
    message=msg
)
```

**관계:**
```
Context: ctx-001
  ├─ Task: task-001 (status: input_required) ← 완료됨
  └─ Task: task-002 (status: completed)      ← 새로 생성
```

#### 3번째 요청 (추가 질문)

```python
# Message
msg = Message(
    text="저그는?",
    message_id="msg-003",
    context_id="ctx-001",  # 같은 Context ID
    reference_task_ids=["task-001", "task-002"]  # 이전 Task들 참조
)

# Task 생성
task = Task(
    task_id="task-003",  # 또 다른 Task ID
    context_id="ctx-001",  # 같은 Context ID
    status="completed",
    message=msg
)
```

**관계:**
```
Context: ctx-001
  ├─ Task: task-001 (status: input_required → completed)
  ├─ Task: task-002 (status: completed)
  └─ Task: task-003 (status: completed) ← 새로 생성
```

---

## A2A 프로토콜의 필드

### Message 필드

```python
class Message:
    message_id: str           # 메시지 고유 ID
    context_id: Optional[str] # 대화 컨텍스트 ID
    task_id: Optional[str]    # 관련 Task ID (선택)
    reference_task_ids: Optional[List[str]]  # 참조 Task ID 목록
```

### Task 필드

```python
class Task:
    task_id: str              # Task 고유 ID
    context_id: Optional[str] # 대화 컨텍스트 ID
    status: TaskStatus        # working, completed, input_required, failed
    message: Message          # 원본 메시지
    artifacts: List[Artifact] # 결과물
```

---

## 전체 흐름

### 1번째 요청: "승률 알려줘"

```
Client (GUI)
    ↓
1. Context ID 생성: "ctx-001"
2. Message 생성:
   - message_id: "msg-001"
   - context_id: "ctx-001"
   - text: "승률 알려줘"
    ↓
KafkaTransport
    ↓
3. Correlation ID 생성: "corr-001"
4. Kafka Produce
    ↓
Server (Data Agent)
    ↓
5. DefaultRequestHandler
   - Task 생성: "task-001"
   - context_id: "ctx-001" (Message에서 복사)
   - status: "input_required"
    ↓
6. AgentExecutor
   - context.context_id: "ctx-001"
   - context.task_id: "task-001"
   - 대화 기록 조회: conversation_history["ctx-001"]
   - 결과: "어떤 종족?"
    ↓
7. Task 업데이트
   - task_id: "task-001"
   - status: "input_required"
   - artifacts: ["어떤 종족?"]
    ↓
Client
    ↓
8. Task 수신 및 표시
```

### 2번째 요청: "테란"

```
Client (GUI)
    ↓
1. Context ID 유지: "ctx-001"
2. Message 생성:
   - message_id: "msg-002"
   - context_id: "ctx-001" (동일!)
   - task_id: "task-001" (선택사항)
   - text: "테란"
    ↓
KafkaTransport
    ↓
3. Correlation ID 생성: "corr-002" (새로 생성!)
4. Kafka Produce
    ↓
Server (Data Agent)
    ↓
5. DefaultRequestHandler
   - Task 생성: "task-002" (새로 생성!)
   - context_id: "ctx-001" (동일!)
   - status: "working"
    ↓
6. AgentExecutor
   - context.context_id: "ctx-001"
   - context.task_id: "task-002"
   - 대화 기록 조회: conversation_history["ctx-001"]
     → ["승률 알려줘", "테란"]
   - 결과: "테란 승률 58%"
    ↓
7. Task 업데이트
   - task_id: "task-002"
   - status: "completed"
   - artifacts: ["테란 승률 58%"]
    ↓
Client
    ↓
8. Task 수신 및 표시
```

---

## 코드로 확인

### GUI에서 Context ID 관리

```python
# gui/balance_gui.py
class BalanceGUI:
    def __init__(self):
        self.context_id = None  # Context ID 저장
        self.task_history = []  # Task 기록
    
    async def send_message(self, user_input):
        # 첫 메시지면 Context ID 생성
        if self.context_id is None:
            self.context_id = str(uuid4())
        
        # Message 생성
        msg = Message(
            text=user_input,
            message_id=uuid4().hex,
            context_id=self.context_id  # Context ID 포함
        )
        
        # Transport 호출
        async for event in self.transport.send_message_streaming(msg):
            if isinstance(event, Task):
                # Task 기록 저장
                self.task_history.append({
                    "task_id": event.task_id,
                    "context_id": event.context_id,
                    "status": event.status
                })
            yield event
```

### DefaultRequestHandler에서 Task 생성

```python
# a2a/server/request_handlers.py (SDK)
class DefaultRequestHandler:
    async def on_message_send_stream(self, params):
        # 1. Task 생성
        task = await self.task_store.create_task(
            task_id=str(uuid4()),  # 새로운 Task ID
            message=params.message,
            status=TaskStatus(state=TaskState.working)
        )
        
        # 2. Message의 context_id를 Task에 복사
        if params.message.context_id:
            task.context_id = params.message.context_id
        
        # 3. Task yield
        yield task
        
        # 4. RequestContext 생성
        context = RequestContext(
            task_id=task.task_id,
            context_id=task.context_id,  # Context ID 전달
            message=params.message
        )
        
        # 5. AgentExecutor 실행
        await self.agent_executor.execute(context, event_queue)
```

### AgentExecutor에서 Context 사용

```python
# agents/data_analysis_agent_executor.py
class DataAnalysisExecutor(AgentExecutor):
    def __init__(self):
        self.conversation_history = {}  # context_id → 대화 기록
    
    async def execute(self, context: RequestContext, event_queue):
        # Context ID와 Task ID 모두 사용 가능
        context_id = context.context_id  # "ctx-001"
        task_id = context.task_id        # "task-001", "task-002", ...
        
        # Context ID로 대화 기록 조회
        if context_id:
            history = self.conversation_history.get(context_id, [])
            
            # 현재 메시지 추가
            history.append({
                "task_id": task_id,
                "message": context.message.parts[0].text
            })
            
            # 대화 기록 저장
            self.conversation_history[context_id] = history
            
            print(f"Context: {context_id}")
            print(f"Task: {task_id}")
            print(f"History: {len(history)} messages")
        
        # 작업 수행
        result = await self.process(context.message, history)
        
        # 이벤트 발행
        await event_queue.enqueue_event(TaskArtifactUpdateEvent(
            taskId=task_id,
            contextId=context_id,
            artifact=Artifact(parts=[TextPart(text=result)])
        ))
```

---

## 비교표

| 항목 | Context ID | Task ID | Correlation ID |
|------|-----------|---------|----------------|
| **목적** | 대화 세션 식별 | 작업 추적 | 요청-응답 매칭 |
| **범위** | 전체 대화 | 단일 요청 | 단일 Kafka 메시지 |
| **생성** | 대화 시작 시 | 요청마다 | 요청마다 |
| **생성자** | GUI/Client | DefaultRequestHandler | KafkaTransport |
| **위치** | Message, Task | Task | Kafka Key |
| **A2A 표준** | ✅ | ✅ | ❌ (Kafka 전용) |
| **예시** | "ctx-001" | "task-001" | "corr-001" |

---

## 실제 데이터 구조

### 1번째 요청

```json
// Message
{
  "message_id": "msg-001",
  "context_id": "ctx-001",
  "text": "승률 알려줘"
}

// Task
{
  "task_id": "task-001",
  "context_id": "ctx-001",
  "status": "input_required",
  "message": { /* msg-001 */ }
}

// Kafka
{
  "key": "corr-001",  // Correlation ID
  "value": {
    "task_id": "task-001",
    "context_id": "ctx-001"
  }
}
```

### 2번째 요청

```json
// Message
{
  "message_id": "msg-002",
  "context_id": "ctx-001",  // 동일!
  "task_id": "task-001",    // 이전 Task 참조
  "text": "테란"
}

// Task
{
  "task_id": "task-002",    // 새로 생성!
  "context_id": "ctx-001",  // 동일!
  "status": "completed",
  "message": { /* msg-002 */ }
}

// Kafka
{
  "key": "corr-002",  // 새로운 Correlation ID
  "value": {
    "task_id": "task-002",
    "context_id": "ctx-001"
  }
}
```

---

## 대화 기록 관리

### Context ID 기반 저장

```python
conversation_history = {
    "ctx-001": [
        {
            "task_id": "task-001",
            "message": "승률 알려줘",
            "response": "어떤 종족?",
            "status": "input_required"
        },
        {
            "task_id": "task-002",
            "message": "테란",
            "response": "테란 승률 58%",
            "status": "completed"
        },
        {
            "task_id": "task-003",
            "message": "저그는?",
            "response": "저그 승률 42%",
            "status": "completed"
        }
    ]
}
```

### Task ID로 개별 조회

```python
task_store = {
    "task-001": Task(
        task_id="task-001",
        context_id="ctx-001",
        status="input_required"
    ),
    "task-002": Task(
        task_id="task-002",
        context_id="ctx-001",
        status="completed"
    ),
    "task-003": Task(
        task_id="task-003",
        context_id="ctx-001",
        status="completed"
    )
}
```

---

## 사용 패턴

### 패턴 1: 단순 멀티턴 (Context ID만)

```python
# 1번째
msg1 = Message(text="안녕", context_id="ctx-1")
# → Task(task_id="task-1", context_id="ctx-1")

# 2번째
msg2 = Message(text="이름은?", context_id="ctx-1")
# → Task(task_id="task-2", context_id="ctx-1")
```

### 패턴 2: Task 참조 (task_id 사용)

```python
# 1번째
msg1 = Message(text="분석해줘", context_id="ctx-1")
# → Task(task_id="task-1", status="input_required")

# 2번째 (이전 Task 참조)
msg2 = Message(
    text="테란",
    context_id="ctx-1",
    task_id="task-1"  # 이전 Task 참조
)
# → Task(task_id="task-2", context_id="ctx-1")
```

### 패턴 3: 여러 Task 참조 (reference_task_ids)

```python
# 여러 분석 후 종합
msg = Message(
    text="이전 분석들을 종합해줘",
    context_id="ctx-1",
    reference_task_ids=["task-1", "task-2", "task-3"]
)
# → Task(task_id="task-4", context_id="ctx-1")
```

---

## 정리

### Context ID와 Task의 관계

```
1 Context ID = N Tasks

Context: ctx-001 (대화 세션)
  ├─ Task: task-001 (요청 1)
  ├─ Task: task-002 (요청 2)
  └─ Task: task-003 (요청 3)
```

### 생명주기

```
대화 시작
  ↓
Context ID 생성: "ctx-001"
  ↓
요청 1 → Task 1 생성: "task-001" (context_id="ctx-001")
  ↓
요청 2 → Task 2 생성: "task-002" (context_id="ctx-001")
  ↓
요청 3 → Task 3 생성: "task-003" (context_id="ctx-001")
  ↓
대화 종료
```

### 핵심

- **Context ID**: 대화 전체를 묶음
- **Task ID**: 각 요청을 추적
- **Correlation ID**: Kafka 메시지 매칭 (Transport 계층)

**3개의 ID가 협력하여 멀티턴 대화 구현!**

| ID | 목적 | 범위 | A2A 표준 |
|----|------|------|---------|
| Context ID | 대화 세션 | 전체 대화 | ✅ |
| Task ID | 작업 추적 | 단일 요청 | ✅ |
| Correlation ID | 메시지 매칭 | Kafka 메시지 | ❌ |
