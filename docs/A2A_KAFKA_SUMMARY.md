# A2A + Kafka 구현 요약 (PPT 1장)

## 핵심 질문
**"A2A 프로토콜을 Kafka로 구현하면 무엇이 달라지는가?"**

---

## HTTP vs Kafka 비교

### 🔴 기존 방식 (HTTP)

```
Balance Agent ──HTTP──> Data Agent (http://localhost:9003)
              ──HTTP──> CS Agent (http://localhost:9002)
```

**문제점:**
- ❌ N² 연결 (에이전트 N개 → N×(N-1) 연결)
- ❌ URL 관리 필요 (각 에이전트 주소 알아야 함)
- ❌ 장애 전파 (한 에이전트 다운 → 연결된 모든 에이전트 영향)
- ❌ 메시지 손실 (HTTP는 영속성 없음)
- ❌ 확장 어려움 (에이전트 추가 시 모든 연결 재설정)

### 🟢 Kafka 방식

```
Balance Agent ──┐
                ├──> Kafka Hub ──┐
Data Agent ─────┤                ├──> 모든 Agent
CS Agent ───────┘                │
```

**장점:**
- ✅ N+M 연결 (에이전트 N개 + Kafka M개 = 선형 증가)
- ✅ URL 불필요 (Topic 이름만 알면 됨)
- ✅ 장애 격리 (한 에이전트 다운 → 다른 에이전트 영향 없음)
- ✅ 메시지 영속성 (Kafka 로그에 모든 통신 기록)
- ✅ 확장 용이 (에이전트 추가 시 Kafka만 연결)

---

## 구현 핵심

### 1. Transport 계층만 교체

```
┌─────────────────────────────────────┐
│  A2A 프로토콜 (변경 없음)           │
│  - Task 관리                        │
│  - 멀티턴 대화                      │
│  - 스트리밍                         │
│  - DefaultRequestHandler            │
└─────────────────────────────────────┘
            ↓ 교체
┌─────────────────────────────────────┐
│  Transport 계층                     │
│  HTTP → Kafka                       │
└─────────────────────────────────────┘
```

**핵심:** 비즈니스 로직은 그대로, Transport만 변경!

### 2. 3가지 핵심 구현

#### ① KafkaTransport (Client-side)
```python
class KafkaTransport(ClientTransport):
    """HTTP 대신 Kafka로 통신"""
    
    async def send_message_streaming(self, request):
        # 1. Correlation ID 생성 (요청-응답 매칭)
        correlation_id = str(uuid4())
        
        # 2. Kafka Produce (요청 발행)
        await self.producer.send(
            f"agent.{target}.requests",
            key=correlation_id,
            value=request
        )
        
        # 3. Response Queue에서 응답 대기
        while True:
            response = await response_queue.get()
            if response.get("final"):
                break
            yield response
```

#### ② KafkaConsumerHandler (Server-side)
```python
class KafkaConsumerHandler:
    """Kafka 요청을 받아 DefaultRequestHandler로 처리"""
    
    async def start(self):
        # Kafka Consumer로 요청 수신
        async for msg in self.consumer:
            # DefaultRequestHandler 호출 (재사용!)
            async for event in self.request_handler.on_message_send_stream(params):
                # Kafka로 응답 발행
                await self.producer.send(
                    f"agent.{name}.responses",
                    key=correlation_id,
                    value=event
                )
```

#### ③ Agent Discovery (agent.cards)
```python
# 에이전트 시작 시 Card 발행
await producer.send(
    "agent.cards",
    key="data",
    value={
        "name": "Data Analysis Agent",
        "skills": [{"name": "analyze_game_stats", ...}]
    }
)

# Balance Agent가 구독하여 Tool 동적 생성
cards = await discover_agents()
for agent_id, card in cards.items():
    for skill in card['skills']:
        tool = create_agent_tool(agent_id, skill)
        tools.append(tool)
```

---

## 3개의 ID로 멀티턴 대화 구현

| ID | 목적 | 범위 | 생성 시점 |
|----|------|------|----------|
| **Context ID** | 대화 세션 식별 | 전체 대화 | 대화 시작 (A2A 표준) |
| **Task ID** | 작업 추적 | 단일 요청 | 요청마다 (A2A 표준) |
| **Correlation ID** | 메시지 매칭 | Kafka 메시지 | 요청마다 (Kafka 전용) |

```
요청 1: context_id="ctx-001", task_id="task-001", correlation_id="corr-001"
요청 2: context_id="ctx-001", task_id="task-002", correlation_id="corr-002"
요청 3: context_id="ctx-001", task_id="task-003", correlation_id="corr-003"
```

---

## 성과

### ✅ A2A 프로토콜 완전 유지
- 실시간 thinking 스트리밍
- 멀티턴 대화 (Context ID)
- Task 관리 (DefaultRequestHandler 재사용)
- 동기/비동기 모두 지원

### ✅ Kafka 장점 활용
- Hub-Spoke 아키텍처 (N² → N+M)
- 메시지 영속성 (감사 로그, 디버깅, 재생)
- 느슨한 결합 (URL 불필요, 장애 격리)
- 동적 Discovery (agent.cards)

### ✅ 코드 변경 최소
- Transport만 교체 (KafkaTransport, KafkaConsumerHandler)
- 비즈니스 로직 그대로 (AgentExecutor 동일)
- DefaultRequestHandler 재사용 (Task 관리 자동)

---

## 결론

### 핵심 메시지
**"A2A 프로토콜의 모든 기능을 유지하면서 Kafka의 확장성과 영속성을 활용"**

### 기술적 성과
1. **Transport 추상화 성공**: HTTP/Kafka 모두 동일한 A2A 프로토콜 사용
2. **SDK 재사용**: DefaultRequestHandler, EventQueue, TaskStore 그대로 활용
3. **확장 가능한 아키텍처**: Hub-Spoke로 선형 확장 (N² → N+M)

### 비즈니스 가치
- **확장성**: 에이전트 추가 시 Kafka만 연결 (설정 최소화)
- **안정성**: 메시지 영속성으로 손실 방지, 장애 격리
- **운영성**: 모든 통신 기록 저장 (감사, 디버깅, 분석)

### 다음 단계
- MSK 배포 (프로덕션 환경)
- 모니터링 (Prometheus + Grafana)
- 성능 최적화 (배치, 압축)

---

## 한 줄 요약

**"HTTP 대신 Kafka를 사용하여 A2A 프로토콜의 모든 기능을 유지하면서 확장 가능하고 안정적인 멀티 에이전트 시스템 구현"**

---

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────┐
│                    Kafka Hub (MSK)                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Topics:                                         │  │
│  │  - agent.cards (AgentCard 발행)                 │  │
│  │  - agent.{name}.requests (요청)                 │  │
│  │  - agent.{name}.responses (응답)                │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
           ▲              ▲              ▲
           │              │              │
    ┌──────┴──────┐ ┌────┴─────┐ ┌─────┴──────┐
    │   Balance   │ │   Data   │ │     CS     │
    │   Agent     │ │  Agent   │ │   Agent    │
    │  (Client)   │ │ (Server) │ │  (Server)  │
    │             │ │          │ │            │
    │ Kafka       │ │ Kafka    │ │ Kafka      │
    │ Transport   │ │ Consumer │ │ Consumer   │
    │             │ │ Handler  │ │ Handler    │
    └─────────────┘ └──────────┘ └────────────┘
         │                │              │
         └────────────────┴──────────────┘
                         │
                  DefaultRequestHandler
                  (A2A SDK - 재사용)
```

---

## 핵심 코드 (3줄 요약)

```python
# 1. Client: KafkaTransport로 요청
transport = KafkaTransport(target_agent_name="data")
async for event in transport.send_message_streaming(msg):
    yield event

# 2. Server: KafkaConsumerHandler로 수신 → DefaultRequestHandler로 처리
handler = KafkaConsumerHandler("data", DataAnalysisExecutor())
async for event in self.request_handler.on_message_send_stream(params):
    await self.producer.send(f"agent.data.responses", value=event)

# 3. Discovery: agent.cards로 동적 Tool 생성
cards = await discover_agents()  # agent.cards 구독
tools = [create_agent_tool(id, skill) for id, card in cards.items() for skill in card['skills']]
```
