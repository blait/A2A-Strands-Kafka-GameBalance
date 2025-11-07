# A2A 프로토콜 Kafka Transport 구현 요약

## 프로젝트 개요

Google A2A 프로토콜을 AWS MSK(Kafka)를 통해 구현한 게임 밸런스 자동화 시스템

**핵심 성과:**
- ✅ A2A 프로토콜의 모든 기능 유지 (스트리밍, 멀티턴, Task 관리)
- ✅ HTTP 대신 Kafka를 전송 계층으로 사용
- ✅ 에이전트 코드 최소 변경 (Transport만 교체)
- ✅ Hub-Spoke 아키텍처로 확장성 확보

---

## 아키텍처

### Hub-Spoke 구조

```
┌─────────────────────────────────────────────────────────┐
│                    Kafka Hub (MSK)                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Topics:                                         │  │
│  │  - agent.cards (AgentCard 발행)                 │  │
│  │  - agent.balance.requests                        │  │
│  │  - agent.balance.responses                       │  │
│  │  - agent.data.requests                           │  │
│  │  - agent.data.responses                          │  │
│  │  - agent.cs.requests                             │  │
│  │  - agent.cs.responses                            │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
           ▲              ▲              ▲
           │              │              │
    ┌──────┴──────┐ ┌────┴─────┐ ┌─────┴──────┐
    │   Balance   │ │   Data   │ │     CS     │
    │   Agent     │ │  Agent   │ │   Agent    │
    │  (Client)   │ │ (Server) │ │  (Server)  │
    └─────────────┘ └──────────┘ └────────────┘
         │                │              │
         └────────────────┴──────────────┘
                         │
                  agent.cards에
                  AgentCard 발행
```

### 메시지 흐름

```
1. Balance Agent (Client)
   └─> Kafka Produce: agent.data.requests
       Key: correlation-id-123
       Value: {"method": "send_message", "params": {...}}

2. Kafka Hub
   └─> 메시지 저장 (영속성)

3. Data Agent (Server)
   └─> Kafka Consume: agent.data.requests
   └─> DefaultRequestHandler 처리
   └─> Kafka Produce: agent.data.responses
       Key: correlation-id-123
       Value: {"task_id": "...", "artifacts": [...]}

4. Balance Agent
   └─> Kafka Consume: agent.data.responses
   └─> Correlation ID 매칭
   └─> 응답 반환
```

---

## 핵심 구현

### 1. KafkaTransport (Client-side)

**역할:** A2A Client가 Kafka를 통해 다른 에이전트와 통신

**파일:** `kafka/kafka_transport.py`

**동작 원리:**

Balance Agent가 Data Agent를 호출할 때:
1. **요청 발행**: `agent.data.requests` topic에 메시지 발행 (Kafka Producer)
2. **고유 ID 생성**: Correlation ID로 요청-응답 매칭
3. **응답 대기**: `agent.data.responses` topic 구독 (Kafka Consumer)
4. **백그라운드 수신**: 별도 Task에서 응답 계속 수신
5. **매칭 및 전달**: Correlation ID가 일치하는 응답을 요청자에게 전달

**핵심 로직:**

```python
class KafkaTransport(ClientTransport):
    """Kafka-based transport for A2A protocol."""
    
    def __init__(self, target_agent_name: str, bootstrap_servers: str):
        self.target_agent_name = target_agent_name
        self.bootstrap_servers = bootstrap_servers
        self.producer = None  # 요청 발행용
        self.consumer = None  # 응답 수신용
        self._pending_responses = {}  # correlation_id -> Queue
    
    async def send_message_streaming(self, request, context=None):
        """스트리밍 메시지 전송"""
        # 1. Correlation ID 생성
        correlation_id = str(uuid4())
        response_queue = asyncio.Queue()
        self._pending_responses[correlation_id] = response_queue
        
        # 2. Kafka에 요청 발행
        await self.producer.send(
            f"agent.{self.target_agent_name}.requests",
            key=correlation_id.encode(),
            value=payload
        )
        
        # 3. 응답 스트리밍
        while True:
            response = await response_queue.get()
            
            if response.get("final"):
                break
            
            # 이벤트 타입에 따라 객체 생성
            if response.get("type") == "Task":
                yield Task(**response)
            elif response.get("type") == "Message":
                yield Message(**response)
            elif response.get("type") == "TaskStatusUpdateEvent":
                yield TaskStatusUpdateEvent(**response)
            elif response.get("type") == "TaskArtifactUpdateEvent":
                yield TaskArtifactUpdateEvent(**response)
    
    async def _consume_responses(self):
        """백그라운드 응답 수신"""
        async for msg in self.consumer:
            correlation_id = msg.key.decode()
            if correlation_id in self._pending_responses:
                await self._pending_responses[correlation_id].put(msg.value)
```

**핵심 개념:**

1. **Correlation ID로 요청-응답 매칭**:
   - 문제: Kafka는 비동기 메시징이라 어떤 응답이 어떤 요청의 답인지 모름
   - 해결: 각 요청마다 고유 ID 생성 → Kafka 메시지 Key로 사용
   - 응답 수신 시: Key를 보고 어떤 요청의 답인지 판단
   - 예: "abc-123" 요청 → "abc-123" 응답 매칭

2. **비동기 응답 처리 (Producer-Consumer 분리)**:
   - Producer: 요청만 발행하고 바로 리턴
   - Consumer: 백그라운드에서 계속 응답 수신
   - Queue: 요청자와 Consumer를 연결하는 다리
   - 흐름: 요청 → Queue 생성 → Producer 발행 → Consumer 수신 → Queue에 넣기 → 요청자가 Queue에서 꺼내기

3. **스트리밍 지원 (여러 개의 응답)**:
   - 일반 메시지: 요청 1개 → 응답 1개
   - 스트리밍: 요청 1개 → 응답 N개 (thinking, 중간 결과, 최종 결과)
   - `final=false`: 아직 더 올 예정
   - `final=true`: 마지막 응답, 스트림 종료

---

### 2. KafkaConsumerHandler (Server-side)

**역할:** Kafka 요청을 받아 DefaultRequestHandler로 처리

**파일:** `kafka/kafka_consumer_handler.py`

**동작 원리:**

Data Agent가 요청을 처리할 때:
1. **요청 수신**: `agent.data.requests` topic 구독 (Kafka Consumer)
2. **요청 파싱**: Correlation ID와 메시지 내용 추출
3. **A2A 처리**: DefaultRequestHandler에게 위임 (Task 생성, Executor 실행)
4. **이벤트 스트리밍**: Executor가 생성하는 이벤트를 하나씩 Kafka로 전송
5. **응답 발행**: `agent.data.responses` topic에 결과 발행 (Kafka Producer)

**핵심 로직:**

```python
class KafkaConsumerHandler:
    """Kafka Consumer that wraps DefaultRequestHandler."""
    
    def __init__(self, agent_name, agent_executor, task_store=None):
        self.agent_name = agent_name
        
        # DefaultRequestHandler 재사용!
        self.request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=task_store or InMemoryTaskStore()
        )
        
        self.consumer = None
        self.producer = None
    
    async def start(self):
        """Kafka 요청 수신 시작"""
        # Consumer 시작
        self.consumer = AIOKafkaConsumer(
            f"agent.{self.agent_name}.requests",
            bootstrap_servers=self.bootstrap_servers
        )
        await self.consumer.start()
        
        # Producer 시작
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers
        )
        await self.producer.start()
        
        # 메시지 처리 루프
        async for msg in self.consumer:
            asyncio.create_task(self._handle_request(msg))
    
    async def _handle_request(self, msg):
        """요청 처리"""
        correlation_id = msg.key.decode()
        request = msg.value
        method = request.get("method")
        params = request.get("params")
        
        try:
            if method == "send_message_streaming":
                # 스트리밍 처리
                message = Message(**params.get("message", {}))
                async for event in self.request_handler.on_message_send_stream(
                    MessageSendParams(message=message)
                ):
                    # 각 이벤트를 Kafka로 전송
                    event_data = event.model_dump()
                    event_data["type"] = event.__class__.__name__
                    await self._send_response(correlation_id, event_data, final=False)
                
                # 완료 신호
                await self._send_response(correlation_id, {"final": True}, final=True)
                
        except Exception as e:
            await self._send_response(correlation_id, {"error": str(e)}, final=True)
    
    async def _send_response(self, correlation_id: str, response: dict, final: bool):
        """응답 전송"""
        response_data = {**response, "final": final}
        await self.producer.send(
            f"agent.{self.agent_name}.responses",
            key=correlation_id.encode(),
            value=response_data
        )
```

**핵심 개념:**

1. **DefaultRequestHandler 재사용 (코드 중복 제거)**:
   - A2A 프로토콜의 표준 RequestHandler를 그대로 사용
   - Task 생성, Executor 실행, 이벤트 수집이 자동으로 처리됨
   - HTTP든 Kafka든 동일한 비즈니스 로직 사용
   - 장점: Transport만 바꾸면 되고, 에이전트 로직은 수정 불필요

2. **스트리밍 이벤트 전달 (실시간 thinking 표시)**:
   - `on_message_send_stream()`: 이벤트를 하나씩 yield
   - 각 이벤트마다 즉시 Kafka로 전송 (버퍼링 없음)
   - 이벤트 타입을 `type` 필드에 명시 (Task, Message, TaskStatusUpdateEvent 등)
   - Client가 타입을 보고 적절한 객체로 변환

3. **에러 처리 (안정성)**:
   - 예외 발생 시: 에러 메시지를 응답으로 전송
   - `final=true`로 스트림 종료
   - Client가 에러를 Exception으로 변환

---

### 3. Agent Tool 생성 (Balance Agent)

**역할:** 다른 에이전트를 Tool로 래핑하여 Strands Agent에 제공

**파일:** `agents/game_balance_agent_executor.py`

**동작 원리:**

Balance Agent가 다른 에이전트를 호출하는 방법:
1. **AgentCard 조회**: agent.cards에서 모든 에이전트 정보 수집
2. **Tool 동적 생성**: 각 에이전트의 Skill을 Tool 함수로 변환
3. **Strands 등록**: 생성된 Tool들을 Strands Agent에 등록
4. **LLM 호출**: LLM이 필요 시 Tool 자동 호출
5. **응답 수집**: 스트리밍 응답을 모두 모아서 반환

**핵심 로직:**

```python
def create_agent_tool(agent_id: str, skill_name: str, description: str):
    """에이전트를 Tool로 변환"""
    
    async def delegation_function(query: str) -> str:
        # 1. KafkaTransport 가져오기
        transport = a2a_client.get_transport(agent_id)
        
        # 2. 메시지 생성
        msg = Message(
            kind="message",
            role=Role.user,
            parts=[Part(TextPart(kind="text", text=query))],
            message_id=uuid4().hex
        )
        
        # 3. 스트리밍 호출
        response_text = ""
        async for event in transport.send_message_streaming(MessageSendParams(message=msg)):
            if hasattr(event, 'artifact') and event.artifact:
                artifact = event.artifact
                if hasattr(artifact, 'parts') and artifact.parts:
                    for part in artifact.parts:
                        if hasattr(part, 'text'):
                            response_text += part.text
        
        return response_text
    
    # Tool로 등록
    delegation_function.__name__ = skill_name
    delegation_function.__doc__ = description
    return tool(delegation_function)

# Agent 생성 시 Tool 등록
async def create_agent():
    await a2a_client.init()
    
    tools = []
    for agent_id, card in a2a_client.agent_cards.items():
        if agent_id == "balance":
            continue
        
        for skill in card.get('skills', []):
            tool_func = create_agent_tool(agent_id, skill['name'], skill['description'])
            tools.append(tool_func)
    
    return Agent(
        name="Game Balance Agent",
        model=BedrockModel(model_id="us.amazon.nova-lite-v1:0"),
        tools=tools,
        system_prompt="..."
    )
```

**핵심 개념:**

1. **동적 Tool 생성 (확장성)**:
   - AgentCard에서 Skill 정보 자동 추출
   - 각 Skill을 Tool 함수로 변환 (함수 이름, docstring 설정)
   - Strands Agent에 등록하면 LLM이 자동으로 사용
   - 새 에이전트 추가 시: Card만 발행하면 Tool 자동 생성

2. **스트리밍 응답 수집 (완전한 답변)**:
   - `send_message_streaming()` 사용하여 모든 이벤트 수신
   - Artifact의 텍스트만 추출하여 누적
   - 최종 응답을 Tool 결과로 반환
   - LLM은 완성된 답변만 받음

3. **에이전트 간 통신 (투명성)**:
   - Balance Agent → Kafka → Data/CS Agent
   - 응답 수신 → Tool 결과로 반환
   - Strands Agent가 Tool 결과를 활용하여 최종 답변 생성
   - 사용자는 에이전트 간 통신을 의식하지 않음

---

### 4. Agent Discovery (Agent Registry)

**역할:** Kafka를 통해 에이전트 발견 및 AgentCard 조회

**파일:** `kafka/agent_registry.py`

**동작 원리:**

에이전트 Discovery 과정:
1. **Card 발행**: 각 에이전트가 시작 시 agent.cards에 자신의 Card 발행
2. **Card 수집**: Balance Agent가 agent.cards topic 구독
3. **Compaction**: Kafka가 같은 Key의 최신 값만 유지 (중복 제거)
4. **Tool 생성**: 수집된 Card로 Tool 동적 생성
5. **자동 업데이트**: 새 에이전트 추가 시 자동으로 Tool 추가

**핵심 로직:**

```python
async def discover_agents(bootstrap_servers: str = "localhost:9092") -> dict:
    """Kafka agent.cards topic에서 AgentCard 조회"""
    
    consumer = AIOKafkaConsumer(
        "agent.cards",
        bootstrap_servers=bootstrap_servers,
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset='earliest',  # 처음부터 읽기
        enable_auto_commit=False
    )
    await consumer.start()
    
    agent_cards = {}
    
    try:
        # Compacted topic에서 최신 Card만 읽기
        async for msg in consumer:
            agent_id = msg.key.decode()
            card_data = msg.value
            
            # Tombstone (삭제) 메시지 처리
            if card_data is None:
                agent_cards.pop(agent_id, None)
            else:
                agent_cards[agent_id] = card_data
            
            # 모든 메시지 읽었으면 종료
            if consumer.highwater(msg.partition) == msg.offset + 1:
                break
    finally:
        await consumer.stop()
    
    return agent_cards


async def publish_agent_card(
    agent_id: str,
    card: dict,
    bootstrap_servers: str = "localhost:9092"
):
    """에이전트 시작 시 AgentCard를 agent.cards에 발행"""
    
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode()
    )
    await producer.start()
    
    try:
        await producer.send(
            "agent.cards",
            key=agent_id.encode(),
            value=card
        )
        print(f"✅ Published AgentCard for {agent_id}")
    finally:
        await producer.stop()
```

**에이전트 시작 시 Card 발행:**

```python
# data_analysis_agent.py

async def main():
    # 1. AgentCard 정의
    agent_card = {
        "name": "Data Analysis Agent",
        "description": "게임 통계 데이터 분석",
        "skills": [
            {
                "name": "analyze_game_stats",
                "description": "게임 로그를 분석하여 종족별 승률, 픽률 등을 계산"
            }
        ]
    }
    
    # 2. Kafka에 Card 발행
    await publish_agent_card("data", agent_card)
    
    # 3. Kafka Consumer 시작
    kafka_handler = KafkaConsumerHandler("data", DataAnalysisExecutor())
    await kafka_handler.start()
```

**핵심 개념:**

1. **agent.cards Topic (Compacted) - 중앙 집중식 Card 저장소**:
   - Key: agent_id (예: "data", "cs")
   - Value: AgentCard JSON (name, description, skills)
   - Compaction: 같은 Key의 최신 값만 유지 (디스크 절약)
   - 에이전트 시작 시 Card 발행 → 자동으로 등록됨

2. **동적 Discovery (URL 불필요)**:
   - Balance Agent가 agent.cards 구독하여 모든 Card 수집
   - 에이전트 추가: Card만 발행하면 자동 발견
   - 에이전트 제거: Tombstone 메시지 (value=null) 발행
   - HTTP GET /card 불필요, URL 설정 불필요

3. **HTTP GET /card 대체 (분산 시스템 장점)**:
   - HTTP: 각 에이전트에 직접 연결하여 Card 조회 (N번 요청)
   - Kafka: agent.cards에서 한 번에 모든 Card 조회 (1번 요청)
   - 중앙 집중식 Card 저장소로 관리 간편
   - 에이전트 간 의존성 제거 (느슨한 결합)

---

## HTTP vs Kafka 비교

### Discovery & 초기화

| 단계 | HTTP | Kafka |
|------|------|-------|
| **에이전트 주소** | URL 필요 (http://localhost:9003) | Agent 이름만 필요 (data) |
| **AgentCard 조회** | HTTP GET /card | agent.cards topic 구독 |
| **Card 저장** | 메모리 (Balance Agent) | Kafka (Compacted topic) |
| **연결 확인** | 초기화 시 확인 | 지연 확인 (첫 요청 시) |
| **에이전트 추가** | URL 설정 필요 | Card 발행만 하면 자동 |
| **코드 복잡도** | 높음 (HTTP client, resolver) | 낮음 (Kafka consumer) |

### 메시지 전송

| 단계 | HTTP | Kafka |
|------|------|-------|
| **요청 전송** | HTTP POST /v1/message:send | Kafka Produce |
| **응답 수신** | HTTP Response | Kafka Consume |
| **Correlation** | HTTP 세션 | Correlation ID |
| **스트리밍** | Server-Sent Events | Kafka 메시지 스트림 |
| **영속성** | 없음 | Kafka 로그에 저장 |

### Task 관리

| 항목 | HTTP | Kafka |
|------|------|-------|
| **Task 생성** | DefaultRequestHandler | DefaultRequestHandler (동일) |
| **Task 저장** | InMemoryTaskStore | InMemoryTaskStore (동일) |
| **코드 수정** | 불필요 | 불필요 |

---

## 주요 해결 과제

### 1. Correlation ID 매칭

**문제:** 
- Kafka는 비동기 메시징이라 요청과 응답이 분리됨
- 여러 요청이 동시에 발생하면 어떤 응답이 어떤 요청의 답인지 알 수 없음
- 예: Balance Agent가 Data와 CS를 동시에 호출하면 응답이 섞임

**해결:**
```python
# 요청 시: 고유 ID 생성 및 Queue 준비
correlation_id = str(uuid4())  # "abc-123"
self._pending_responses[correlation_id] = asyncio.Queue()

# Kafka 메시지 Key로 사용
await self.producer.send(
    topic="agent.data.requests",
    key=correlation_id.encode(),  # Key에 ID 저장
    value=payload
)

# 응답 수신 시: Key를 보고 매칭
async for msg in self.consumer:
    correlation_id = msg.key.decode()  # "abc-123"
    if correlation_id in self._pending_responses:
        # 해당 요청의 Queue에 응답 전달
        await self._pending_responses[correlation_id].put(msg.value)
```

**핵심:**
- 각 요청마다 UUID 생성 → Kafka Key로 사용
- 응답의 Key를 보고 어떤 요청의 답인지 판단
- Dictionary로 요청별 Queue 관리 (요청 ID → Queue)
- 동시 요청도 정확히 매칭됨

### 2. 스트리밍 이벤트 전달

**문제:** 
- 실시간 thinking 표시를 위해 중간 결과를 계속 전달해야 함
- Kafka는 메시지 단위로 전송되므로 스트림을 어떻게 표현할지 고민
- 언제 스트림이 끝났는지 알아야 함

**해결:**
```python
# Server-side: 각 이벤트마다 Kafka 메시지 전송
async for event in self.request_handler.on_message_send_stream(params):
    event_data = event.model_dump()
    event_data["type"] = event.__class__.__name__  # 이벤트 타입 명시
    event_data["final"] = False  # 아직 더 올 예정
    await self._send_response(correlation_id, event_data)

# 마지막 메시지: 스트림 종료 신호
await self._send_response(correlation_id, {"final": True})

# Client-side: 이벤트 타입에 따라 객체 생성
while True:
    response = await response_queue.get()
    
    if response.get("final"):  # 종료 신호
        break
    
    # 타입별로 적절한 객체 생성
    if response.get("type") == "TaskArtifactUpdateEvent":
        yield TaskArtifactUpdateEvent(**response)
    elif response.get("type") == "TaskStatusUpdateEvent":
        yield TaskStatusUpdateEvent(**response)
```

**핵심:**
- 각 이벤트를 별도 Kafka 메시지로 전송 (버퍼링 없음)
- `type` 필드로 이벤트 종류 구분
- `final` 필드로 스트림 종료 표시
- Client가 타입을 보고 적절한 A2A 객체로 변환

### 3. DefaultRequestHandler 재사용

**문제:** 
- Task 생성, Executor 실행, 이벤트 수집 로직이 복잡함
- HTTP와 Kafka에서 동일한 로직을 중복 구현하면 유지보수 어려움
- A2A 프로토콜의 표준 동작을 직접 구현하면 버그 발생 가능

**해결:**
```python
# HTTP든 Kafka든 동일한 RequestHandler 사용
self.request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,  # 비즈니스 로직
    task_store=task_store            # Task 저장소
)

# Kafka에서도 동일하게 호출
result = await self.request_handler.on_message_send_stream(params)
```

**핵심:**
- A2A SDK의 DefaultRequestHandler를 그대로 사용
- Task 생성, Executor 실행, 이벤트 수집이 자동으로 처리됨
- Transport 계층(HTTP/Kafka)과 비즈니스 로직 완전 분리
- 코드 중복 제거, 버그 감소, 유지보수 용이

### 4. 백그라운드 Consumer 실행

**문제:** 
- 응답을 받으려면 Consumer가 계속 실행되어야 함
- 요청 함수가 블로킹되면 안 됨 (비동기 처리 필요)
- Consumer Task를 언제 시작하고 종료할지 관리 필요

**해결:**
```python
# Consumer를 백그라운드 Task로 실행
async def _ensure_started(self):
    if self.consumer is None:
        self.consumer = AIOKafkaConsumer(...)
        await self.consumer.start()
        
        # 백그라운드에서 계속 응답 수신
        self._consumer_task = asyncio.create_task(self._consume_responses())

async def _consume_responses(self):
    """백그라운드에서 계속 실행"""
    async for msg in self.consumer:
        correlation_id = msg.key.decode()
        if correlation_id in self._pending_responses:
            # 해당 요청의 Queue에 응답 전달
            await self._pending_responses[correlation_id].put(msg.value)

# 종료 시 정리
async def close(self):
    if self._consumer_task:
        self._consumer_task.cancel()  # Task 취소
        await self._consumer_task     # 완료 대기
```

**핵심:**
- `asyncio.create_task()`로 백그라운드 실행
- 요청 함수는 블로킹되지 않고 바로 리턴
- Consumer는 계속 응답을 수신하여 Queue에 전달
- 종료 시 Task를 cancel하여 깔끔하게 정리

---

## 장점

### 1. 확장성
- **HTTP**: N² 연결 (모든 에이전트가 서로 연결)
- **Kafka**: N+M 연결 (에이전트 N개 + Kafka M개)
- 에이전트 추가 시 선형 증가

### 2. 영속성
- 모든 메시지가 Kafka에 저장
- 감사 로그, 디버깅, 재생 가능
- 메시지 손실 방지

### 3. 느슨한 결합
- 에이전트 간 URL 불필요
- 장애 격리 (한 에이전트 다운 시 다른 에이전트 영향 없음)
- 독립적 배포 가능

### 4. A2A 기능 완전 유지
- 실시간 thinking 스트리밍 ✅
- 멀티턴 대화 ✅
- Task 관리 ✅
- 동기/비동기 모두 지원 ✅

### 5. 코드 변경 최소
- Transport만 교체
- 비즈니스 로직 그대로
- DefaultRequestHandler 재사용

---

## 기술 스택

- **메시지 브로커**: Apache Kafka (로컬) / AWS MSK (프로덕션)
- **Kafka Client**: aiokafka (Python 비동기)
- **A2A Protocol**: Google A2A SDK
- **Agent Framework**: AWS Strands
- **LLM**: Amazon Bedrock (Nova Lite)
- **GUI**: Streamlit

---

## 프로젝트 구조

```
game-balance-a2a/
├── kafka/
│   ├── kafka_transport.py           # Client-side Transport
│   ├── kafka_consumer_handler.py    # Server-side Consumer
│   ├── agent_registry.py            # Agent Discovery
│   └── msk_config.py                # Kafka 설정
├── agents/
│   ├── game_balance_agent.py        # Balance Agent (Client)
│   ├── game_balance_agent_executor.py
│   ├── data_analysis_agent.py       # Data Agent (Server)
│   ├── data_analysis_agent_executor.py
│   ├── cs_feedback_agent.py         # CS Agent (Server)
│   └── cs_feedback_agent_executor.py
├── gui/
│   ├── balance_gui.py               # Balance Agent GUI
│   ├── analysis_gui.py              # Data Agent GUI
│   └── cs_gui.py                    # CS Agent GUI
├── docs/
│   ├── KAFKA_TRANSPORT_PLAN.md      # 구현 계획
│   ├── LOGIC_COMPARISON.md          # HTTP vs Kafka 비교
│   ├── TASK_MANAGEMENT.md           # Task 관리
│   └── IMPLEMENTATION_SUMMARY.md    # 이 문서
└── docker-compose.yml               # 로컬 Kafka
```

---

## 실행 방법

### 1. Kafka 시작
```bash
docker-compose up -d
```

### 2. Topic 생성
```bash
python scripts/create_local_topics.py

# 생성되는 Topics:
# - agent.cards (cleanup.policy=compact)  # AgentCard 저장
# - agent.balance.requests
# - agent.balance.responses
# - agent.data.requests
# - agent.data.responses
# - agent.cs.requests
# - agent.cs.responses
```

### 3. 에이전트 시작
```bash
./start_agents.sh
```

### 4. GUI 시작
```bash
./start_gui.sh
```

---

## 데모 시나리오

### 1. 게임 밸런스 분석 요청

**사용자 입력:**
```
테란과 저그의 밸런스를 분석해줘
```

**Balance Agent:**
1. 요청 분석
2. Data Agent 호출 (게임 통계)
3. CS Agent 호출 (유저 피드백)
4. 종합 분석 및 제안

**Kafka 메시지 흐름:**
```
0. 에이전트 시작 시
   Data Agent → Kafka: agent.cards
   Key: "data"
   Value: {name, description, skills}
   
   CS Agent → Kafka: agent.cards
   Key: "cs"
   Value: {name, description, skills}

1. Balance Agent 초기화
   Balance → Kafka: agent.cards 구독
   모든 AgentCard 수집
   Tool 동적 생성

2. Balance → Kafka: agent.data.requests
   "게임 통계 분석해줘"

3. Data Agent 처리
   - 게임 로그 분석
   - 승률 계산

4. Data → Kafka: agent.data.responses
   "테란 승률 58%, 저그 42%"

5. Balance → Kafka: agent.cs.requests
   "유저 피드백 분석해줘"

6. CS Agent 처리
   - 게시판 분석
   - 컴플레인 요약

7. CS → Kafka: agent.cs.responses
   "저그 너프 요청 500건"

8. Balance Agent 종합
   "테란이 강함, 저그 버프 필요"
```

---

## 향후 개선 사항

### 1. MSK 배포
- Terraform으로 MSK 클러스터 생성
- 프로덕션 환경 설정 (SSL, SASL)

### 2. 모니터링
- Kafka 메트릭 수집 (Prometheus)
- 대시보드 구성 (Grafana)
- 에이전트 상태 모니터링

### 3. 성능 최적화
- Kafka Consumer 설정 최적화
- 배치 처리
- 압축 활성화

### 4. 에러 처리
- Dead Letter Queue
- 재시도 로직
- Circuit Breaker

### 5. 동적 Agent Discovery
- ~~Kafka Topic으로 AgentCard 조회~~ ✅ 구현 완료
- ~~에이전트 동적 추가/제거~~ ✅ 구현 완료
- Health Check

---

## 결론

**A2A 프로토콜 + Kafka = 확장 가능한 멀티 에이전트 시스템**

- ✅ A2A의 모든 기능 유지
- ✅ Kafka의 확장성과 영속성 활용
- ✅ 최소한의 코드 변경
- ✅ Hub-Spoke 아키텍처로 N² → N+M 연결

**핵심 구현:**
1. KafkaTransport: Client-side Producer/Consumer
2. KafkaConsumerHandler: Server-side Consumer + DefaultRequestHandler
3. Correlation ID: 요청-응답 매칭
4. 스트리밍: 실시간 이벤트 전달

**결과:**
- HTTP 방식과 동일한 사용자 경험
- Kafka의 장점 (확장성, 영속성, 느슨한 결합) 활용
- 프로덕션 준비 완료
