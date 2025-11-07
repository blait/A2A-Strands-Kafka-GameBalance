# A2A 프로토콜과 Apache Kafka를 활용한 분산 AI 에이전트 시스템 구축

## 들어가며

AI 에이전트 기술이 발전하면서, 단일 에이전트로는 해결하기 어려운 복잡한 문제들을 여러 전문화된 에이전트가 협력하여 해결하는 멀티 에이전트 시스템이 주목받고 있습니다. 하지만 서로 다른 프레임워크나 벤더로 만들어진 에이전트들을 연결하는 것은 쉽지 않았습니다. 각자 다른 API 형식, 다른 통신 방식, 다른 상태 관리 방법을 사용하기 때문입니다.

이러한 문제를 해결하기 위해 Google은 2025년 4월 **A2A(Agent-to-Agent) 프로토콜**을 발표했습니다. A2A는 에이전트 간 상호운용성을 위한 개방형 표준으로, 마치 HTTP가 웹 서버 간 통신을 표준화한 것처럼, AI 에이전트 간 통신을 표준화합니다.

이 글에서는 A2A 프로토콜을 Apache Kafka 위에 구현하여, 확장 가능하고 안정적인 분산 AI 에이전트 시스템을 구축한 사례를 소개합니다. 게임 밸런스 자동화라는 실제 사용 사례를 통해, 이 아키텍처가 어떻게 복잡한 멀티 에이전트 워크플로우를 효과적으로 지원하는지 보여드리겠습니다.

## A2A 프로토콜: 에이전트 상호운용성의 새로운 표준

### HTTP 기반 통신의 구조적 문제

전통적인 멀티 에이전트 시스템은 에이전트 간 직접 HTTP 연결을 사용합니다. 이 방식은 간단해 보이지만, 시스템이 커질수록 여러 문제가 발생합니다.

**연결 복잡도의 기하급수적 증가**

에이전트가 3개일 때는 6개의 연결만 관리하면 되지만, 10개가 되면 90개의 연결을 관리해야 합니다. 각 에이전트는 다른 모든 에이전트의 URL을 알고 있어야 하며, 한 에이전트의 주소가 변경되면 모든 연결을 업데이트해야 합니다.

```
HTTP 방식 (N² 연결):              Kafka 방식 (N+M 연결):
                                 
Balance ──→ Data                      Balance ──┐
   │                                            ├──→ Kafka
   └──────→ CS                        Data ─────┤
                                                 │
Data ──────→ CS                        CS ───────┘
```

**장애 전파의 위험**

한 에이전트에 문제가 생기면, 그 에이전트와 직접 연결된 모든 에이전트가 영향을 받습니다. 타임아웃이 발생하거나 에러가 전파되어 전체 시스템의 안정성이 저하됩니다.

**확장의 어려움**

새로운 에이전트를 추가하려면 기존 에이전트들의 설정을 모두 변경해야 합니다. 로드 밸런싱을 위해 에이전트 인스턴스를 늘리는 것도 복잡한 작업이 됩니다.

## A2A 프로토콜: 에이전트 상호운용성의 새로운 표준

### A2A 프로토콜이란?

Google이 2025년 4월 발표한 A2A(Agent-to-Agent) 프로토콜은 서로 다른 프레임워크나 벤더로 만들어진 AI 에이전트들이 표준화된 방식으로 협력할 수 있게 하는 개방형 프로토콜입니다. Atlassian, Box, Cohere, Intuit, MongoDB, PayPal, Salesforce, SAP, ServiceNow 등 50개 이상의 기술 파트너가 참여하고 있습니다.

**A2A가 해결하는 문제:**

기존에는 각 에이전트 프레임워크마다 다른 API 형식을 사용했습니다:
- LangChain의 에이전트는 LangChain 방식으로 통신
- AutoGPT의 에이전트는 AutoGPT 방식으로 통신
- 커스텀 에이전트는 각자의 방식으로 통신

이는 마치 웹이 HTTP 표준 없이 각 서버가 자신만의 프로토콜을 사용하는 것과 같습니다. A2A는 이를 표준화하여, 어떤 프레임워크로 만들어진 에이전트든 서로 통신할 수 있게 합니다.

### A2A의 핵심 개념

**1. Agent Card (에이전트 카드)**

에이전트가 자신의 능력을 선언하는 JSON 형식의 명세서입니다. 다른 에이전트들은 이를 읽고 어떤 작업을 요청할 수 있는지 파악합니다.

```python
agent_card = {
    "name": "data-agent",
    "description": "게임 통계 데이터 분석 전문가",
    "skills": [
        {
            "id": "get_win_rate",
            "description": "특정 종족의 승률을 조회합니다",
            "parameters": {"race": "string"}
        },
        {
            "id": "get_avg_game_time",
            "description": "평균 게임 시간을 계산합니다"
        }
    ]
}
```

**2. Task (작업)**

에이전트 간 상호작용의 기본 단위입니다. 각 Task는 생명주기를 가지며 상태가 변화합니다:

- `pending`: 작업이 생성되어 대기 중
- `running`: 작업이 실행 중
- `completed`: 작업이 성공적으로 완료됨
- `input-required`: 추가 정보가 필요함 (멀티턴 대화)
- `failed`: 작업이 실패함

**3. Message (메시지)**

에이전트 간 통신의 기본 단위입니다. 각 메시지는:
- `role`: user, assistant, system 등의 역할
- `parts`: 텍스트, 이미지, 오디오 등 다양한 콘텐츠
- `message_id`: 메시지 고유 식별자
- `context_id`: 대화 맥락 유지를 위한 식별자

**4. Artifact (결과물)**

Task의 출력물입니다. 텍스트 응답, 생성된 이미지, 분석 결과 등 다양한 형태가 가능합니다.

### A2A의 설계 원칙

Google은 A2A 프로토콜을 설계하면서 다섯 가지 핵심 원칙을 따랐습니다:

**1. 에이전트 능력 수용**

에이전트를 단순한 "도구"로 제한하지 않고, 메모리, 도구, 컨텍스트를 공유하지 않아도 자연스럽게 협력할 수 있도록 설계했습니다.

**2. 기존 표준 활용**

HTTP, SSE, JSON-RPC 등 널리 사용되는 표준 위에 구축하여 기존 IT 스택과의 통합을 쉽게 했습니다.

**3. 기본 보안**

OpenAPI의 인증 체계와 동등한 수준의 엔터프라이즈급 인증 및 권한 부여를 지원합니다.

**4. 장기 실행 작업 지원**

몇 초 안에 끝나는 간단한 작업부터 사람의 개입이 필요한 며칠짜리 작업까지 유연하게 지원합니다. 실시간 피드백, 알림, 상태 업데이트를 제공합니다.

**5. 모달리티 독립성**

텍스트뿐만 아니라 오디오, 비디오 스트리밍 등 다양한 형태의 콘텐츠를 지원합니다.

### 실제 사용 사례: 채용 프로세스 자동화

Google의 발표에서 소개된 예시를 보면, 소프트웨어 엔지니어 채용 과정이 A2A로 어떻게 간소화되는지 알 수 있습니다:

1. 채용 담당자가 통합 인터페이스에서 "Python 개발자, 시애틀 지역, 5년 경력" 요청
2. 코디네이터 에이전트가 여러 전문 에이전트들과 협력:
   - 채용 플랫폼 에이전트: 후보자 검색
   - 스케줄링 에이전트: 면접 일정 조율
   - 백그라운드 체크 에이전트: 신원 조회
3. 각 단계의 결과가 자동으로 다음 단계로 전달되어 전체 프로세스 완료

이처럼 A2A는 서로 다른 시스템의 에이전트들이 협력하여 복잡한 업무를 자동화할 수 있게 합니다.

## 문제 정의: A2A의 HTTP 전송 계층 한계

### A2A 프로토콜의 기본 전송 방식

A2A 프로토콜은 에이전트 간 상호작용을 표준화했지만, 기본 전송 계층으로 HTTP를 사용합니다. 이는 간단한 구현과 기존 인프라 활용이라는 장점이 있지만, 대규모 멀티 에이전트 시스템에서는 여러 한계를 보입니다.

## 문제 정의: A2A의 HTTP 전송 계층 한계

### A2A 프로토콜의 기본 전송 방식

A2A 프로토콜은 에이전트 간 상호작용을 표준화했지만, 기본 전송 계층으로 HTTP를 사용합니다. 이는 간단한 구현과 기존 인프라 활용이라는 장점이 있지만, 대규모 멀티 에이전트 시스템에서는 여러 한계를 보입니다.

### HTTP 기반 통신의 구조적 문제

**1. 연결 복잡도의 기하급수적 증가**

HTTP 방식에서는 에이전트가 3개일 때 6개의 연결만 관리하면 되지만, 10개가 되면 90개의 연결을 관리해야 합니다. 각 에이전트는 다른 모든 에이전트의 URL을 알고 있어야 하며, 한 에이전트의 주소가 변경되면 모든 연결을 업데이트해야 합니다.

```
HTTP 방식 (N² 연결):              Kafka 방식 (N+M 연결):
                                 
Balance ──→ Data                      Balance ──┐
   │                                            ├──→ Kafka
   └──────→ CS                        Data ─────┤
                                                 │
Data ──────→ CS                        CS ───────┘

에이전트 수에 따른 연결 수:
3개 → 6개 연결                    3개 → 3개 연결
5개 → 20개 연결                   5개 → 5개 연결
10개 → 90개 연결                  10개 → 10개 연결
20개 → 380개 연결 (N² 증가)       20개 → 20개 연결 (N 증가)
```

**2. 동기적 연결의 확장성 문제**

HTTP는 기본적으로 요청-응답 모델입니다. 에이전트 A가 에이전트 B를 호출하면, 응답을 받을 때까지 연결을 유지해야 합니다. 이는 동시 처리 능력을 제한하고 리소스를 낭비합니다.

**3. 장애 전파와 타임아웃 관리**

한 에이전트가 느려지거나 응답하지 않으면, 그 에이전트를 호출한 모든 에이전트가 타임아웃을 기다려야 합니다. 체인 형태의 호출(A → B → C)에서는 문제가 증폭됩니다.

```
Balance Agent → Data Agent (30초 타임아웃)
                    ↓
                  응답 없음
                    ↓
Balance Agent는 30초 동안 블로킹
사용자는 30초 동안 대기
```

**4. 메시지 내구성 부족**

HTTP 요청은 휘발성입니다. 에이전트가 재시작되거나 네트워크 문제가 발생하면 메시지가 손실됩니다. 재시도 로직을 직접 구현해야 하며, 중복 처리 방지도 복잡합니다.

**5. 동적 확장의 어려움**

트래픽이 증가하여 에이전트 인스턴스를 늘리려면:
- 로드 밸런서 설정 필요
- 모든 클라이언트 에이전트가 새 엔드포인트 인지 필요
- 세션 어피니티 관리 복잡

**6. 관찰성과 디버깅의 한계**

각 에이전트 간 HTTP 호출은 독립적으로 발생하므로:
- 전체 메시지 흐름을 추적하기 어려움
- 중앙 집중식 모니터링 구현이 복잡
- 특정 요청이 어떤 경로로 전파되었는지 파악 어려움

**7. 백프레셔 처리 부재**

에이전트가 처리할 수 있는 용량을 초과하는 요청이 들어오면:
- HTTP는 즉시 거부하거나 타임아웃 발생
- 요청을 큐에 보관하여 나중에 처리하는 메커니즘 없음
- 트래픽 급증 시 시스템 전체가 불안정해질 수 있음

이러한 한계들은 **A2A 프로토콜 자체의 문제가 아니라, HTTP 전송 계층의 구조적 한계**입니다. A2A의 핵심 개념(Agent Card, Task, Message, Artifact)은 훌륭하지만, 이를 전달하는 방식에 개선이 필요합니다.

## 솔루션: A2A + Kafka Hub-Spoke 아키텍처

### 핵심 아이디어

우리의 솔루션은 간단하지만 강력한 아이디어에서 출발합니다: **A2A 프로토콜의 전송 계층을 HTTP에서 Kafka로 교체하여, 모든 에이전트 간 통신을 중앙의 Kafka Hub를 통하도록 하는 것**입니다.

```
                    ┌─────────────────┐
                    │   Kafka Hub     │
                    │  (Amazon MSK)   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Balance Agent │    │  Data Agent   │    │   CS Agent    │
│   (Client)    │    │  (Server)     │    │  (Server)     │
│               │    │               │    │               │
│ - 코디네이터   │    │ - 승률 분석    │    │ - 컴플레인    │
│ - Tool 호출   │    │ - 게임시간     │    │ - 피드백      │
└───────────────┘    └───────────────┘    └───────────────┘
```

이 구조에서 각 에이전트는:
- Kafka에만 연결하면 됩니다 (다른 에이전트의 위치를 알 필요 없음)
- 메시지를 토픽에 발행하고 구독하기만 하면 됩니다
- 다른 에이전트의 장애로부터 격리됩니다

### Kafka를 A2A 전송 계층으로 선택한 이유

A2A 프로토콜은 기본적으로 HTTP를 전송 계층으로 사용하도록 설계되었습니다. 하지만 우리는 다음과 같은 이유로 Kafka를 선택했습니다:

**확장성**: HTTP는 N² 연결이 필요하지만, Kafka는 N+M 연결로 선형 확장이 가능합니다.

**내구성**: Kafka는 메시지를 디스크에 저장하므로, 에이전트가 일시적으로 다운되어도 메시지가 손실되지 않습니다.

**비동기 처리**: 에이전트가 즉시 응답할 수 없는 경우에도 메시지를 큐에 보관하여 나중에 처리할 수 있습니다.

**관찰성**: 모든 메시지가 Kafka를 통과하므로 중앙에서 모니터링하고 분석할 수 있습니다.

중요한 점은, **A2A 프로토콜의 핵심 개념(Agent Card, Task, Message, Artifact)은 그대로 유지**하면서 전송 계층만 교체했다는 것입니다:

```python
# A2A의 ClientTransport 인터페이스를 Kafka로 구현
class KafkaTransport(ClientTransport):
    def __init__(self, target_agent_name: str, bootstrap_servers: str):
        self.target_agent_name = target_agent_name
        self.producer = None  # 요청 발송
        self.consumer = None  # 응답 수신
        self._pending_responses = {}  # Correlation ID 매핑
```

이를 통해 A2A 프로토콜의 모든 기능을 Kafka 위에서 구현할 수 있습니다:
- **멀티턴 대화**: Context ID로 대화 맥락 유지
- **작업 상태 관리**: Task 객체의 상태 전환 (pending → running → completed/input-required/failed)
- **스트리밍 응답**: Kafka의 연속 메시지로 긴 답변을 실시간 전달
- **능력 발견**: Agent Registry 토픽으로 Agent Card 공유

### 게임 밸런스 자동화 시나리오

우리가 구현한 시스템은 게임 밸런스 조정을 자동화합니다:

**Balance Agent (코디네이터)**
- 사용자 질문을 받아 어떤 분석이 필요한지 판단
- 필요한 다른 에이전트들을 호출하여 정보 수집
- 수집된 정보를 종합하여 최종 답변 생성

**Data Agent (통계 분석가)**
- 게임 로그에서 승률, 평균 게임 시간 등 통계 추출
- 종족별, 맵별, 시간대별 등 다양한 관점의 분석 제공

**CS Agent (고객 의견 분석가)**
- 게시판의 컴플레인과 피드백 수집
- 유저들이 실제로 느끼는 밸런스 문제 파악

예를 들어, "테란이 너무 강한가요?"라는 질문이 들어오면:
1. Balance Agent가 질문을 받음
2. Data Agent에게 테란 승률 조회
3. CS Agent에게 테란 관련 컴플레인 조회
4. 두 정보를 종합하여 답변 생성

## 아키텍처 상세 설계

### Kafka 토픽 구조

각 에이전트는 두 개의 전용 토픽을 가집니다:

- `agent.{name}.requests`: 이 에이전트로 들어오는 요청
- `agent.{name}.responses`: 이 에이전트가 보내는 응답
- `agent.registry`: 모든 에이전트가 자신의 능력을 공유

이 구조의 장점:
- **명확한 책임**: 각 토픽의 역할이 분명함
- **독립적 확장**: 각 에이전트의 트래픽에 따라 파티션 수 조정 가능
- **격리**: 한 에이전트의 문제가 다른 에이전트의 토픽에 영향 없음

### 요청-응답 매칭: Correlation ID

Kafka는 기본적으로 비동기 메시징 시스템입니다. 하지만 에이전트 간 통신은 종종 동기적 요청-응답 패턴을 필요로 합니다. 이를 해결하기 위해 **Correlation ID**를 사용합니다.

**동작 방식:**

```python
async def send_message(self, request: MessageSendParams) -> Task:
    # 1. 고유한 Correlation ID 생성
    correlation_id = str(uuid4())
    
    # 2. 응답 대기용 Queue 생성
    response_queue = asyncio.Queue()
    self._pending_responses[correlation_id] = response_queue
    
    # 3. Kafka에 요청 발행
    await self.producer.send(
        f"agent.{self.target_agent_name}.requests",
        key=correlation_id.encode(),
        value={"method": "send_message", "params": {...}}
    )
    
    # 4. 응답 대기 (타임아웃 40초)
    response = await asyncio.wait_for(response_queue.get(), timeout=40.0)
    return Task(**response)
```

백그라운드에서는 별도의 태스크가 지속적으로 응답을 수신합니다:

```python
async def _consume_responses(self):
    """백그라운드에서 응답을 지속적으로 수신"""
    async for msg in self.consumer:
        correlation_id = msg.key.decode()
        
        # Correlation ID로 대기 중인 요청 찾기
        if correlation_id in self._pending_responses:
            await self._pending_responses[correlation_id].put(msg.value)
```

이 방식으로 비동기 메시징 위에서 동기적 요청-응답 패턴을 구현합니다.

### 멀티턴 대화: Context ID

Correlation ID는 단일 요청-응답을 매칭하지만, 대화는 여러 턴으로 이어집니다. 이를 위해 **Context ID**를 추가로 사용합니다.

**시나리오 예시:**

```python
# 1턴: 모호한 질문
msg1 = Message(
    role=Role.user,
    parts=[Part(TextPart(text="승률?"))],
    message_id=uuid4().hex,
    context_id="ctx-001"  # 새로 생성
)
result1 = await transport.send_message(MessageSendParams(message=msg1))
# 응답: "어떤 종족?" (input-required 상태)

# 2턴: 명확화 제공
msg2 = Message(
    role=Role.user,
    parts=[Part(TextPart(text="저그"))],
    message_id=uuid4().hex,
    context_id=result1.context_id  # 동일한 Context ID 사용
)
result2 = await transport.send_message(MessageSendParams(message=msg2))
# 응답: "저그 승률 50%"
```

**핵심 차이:**
- **Correlation ID**: 매 요청마다 새로 생성, 요청-응답 매칭용
- **Context ID**: 대화 전체에서 유지, 대화 맥락 보존용

### 동적 에이전트 발견

시스템 시작 시 각 에이전트는 `agent.registry` 토픽에 자신의 정보를 발행합니다:

```python
async def register_agent(agent_id: str, agent_card: dict):
    await producer.send(
        "agent.registry",
        key=agent_id.encode(),
        value={
            "name": agent_card.name,
            "agent_id": agent_id,
            "skills": [{"id": s.id, "description": s.description} 
                      for s in agent_card.skills],
            "capabilities": {"streaming": True, "multi_turn": True}
        }
    )
```

다른 에이전트들은 이 토픽을 읽어 사용 가능한 에이전트를 동적으로 발견합니다. 새로운 에이전트가 추가되면 자동으로 발견되어 사용 가능해집니다.

## 구현 핵심 요소

### KafkaTransport: A2A와 Kafka의 연결고리

A2A 프로토콜의 `ClientTransport` 인터페이스를 Kafka로 구현한 클래스입니다.

**주요 책임:**
- Producer로 요청 메시지 발행
- Consumer로 응답 메시지 수신 (백그라운드)
- Correlation ID로 요청과 응답 매칭
- 타임아웃 관리

**비동기 처리의 핵심:**

별도의 백그라운드 태스크가 지속적으로 응답 토픽을 구독합니다. 응답이 도착하면 Correlation ID를 확인하고, 해당 요청을 기다리는 곳에 전달합니다. 이를 통해 여러 요청을 동시에 처리할 수 있습니다.

### KafkaConsumerHandler: 서버 측 처리

각 에이전트는 자신의 요청 토픽을 구독하는 Consumer를 실행합니다:

```python
class KafkaConsumerHandler:
    async def _handle_request(self, msg):
        correlation_id = msg.key.decode()
        request = msg.value
        
        # A2A 프로토콜에 맞게 처리
        if request["method"] == "send_message_streaming":
            message = Message(**request["params"]["message"])
            
            # DefaultRequestHandler가 Task 생성 및 관리
            async for event in self.request_handler.on_message_send_stream(
                MessageSendParams(message=message)
            ):
                # 응답을 Kafka로 전송
                await self._send_response(correlation_id, event)
```

메시지가 도착하면:
1. A2A 프로토콜에 맞게 파싱
2. `DefaultRequestHandler`에 전달하여 실제 에이전트 로직 실행
3. 결과를 A2A 형식으로 변환
4. 응답 토픽에 발행 (같은 Correlation ID 사용)

### Task 생성과 상태 관리

A2A 프로토콜의 핵심 개념인 Task는 `DefaultRequestHandler`에서 자동으로 생성됩니다. Task는 다음 상태를 가질 수 있습니다:

```
초기 생성 (pending)
    ↓
처리 중 (running)
    ↓
    ├─→ 완료 (completed) - 최종 결과 포함
    ├─→ 추가 입력 필요 (input-required) - 멀티턴 대화
    └─→ 실패 (failed) - 에러 정보 포함
```

이 상태 관리를 통해 복잡한 비동기 작업을 체계적으로 추적할 수 있습니다.

## 단계별 구현 가이드

### 1단계: 환경 설정

Docker Compose로 로컬 Kafka 환경을 구축합니다:

```yaml
version: '3'
services:
  kafka:
    image: apache/kafka:latest
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_NUM_PARTITIONS: 3
```

### 2단계: 에이전트 구현

Data Agent를 예로 들어보겠습니다:

```python
class DataAnalysisExecutor(AgentExecutor):
    @tool
    def get_win_rate(self, race: str) -> str:
        """특정 종족의 승률 조회"""
        if not race:
            return "종족을 지정해주세요 (테란/저그/프로토스)"
        
        # 게임 데이터에서 승률 계산
        wins = sum(1 for g in self.game_data if g['race'] == race and g['result'] == 'win')
        total = len([g for g in self.game_data if g['race'] == race])
        win_rate = (wins / total) * 100
        
        return f"{race}의 승률: {win_rate:.1f}%"
    
    async def execute(self, request_context: RequestContext):
        agent = Agent(
            model=BedrockModel(model_id="anthropic.claude-3-sonnet-20240229-v1:0"),
            system_prompt="게임 데이터 분석 전문가입니다.",
            tools=[self.get_win_rate, self.get_avg_game_time]
        )
        
        async for chunk in agent.stream_async(request_context.message.text):
            yield chunk
```

### 3단계: Kafka 연결

각 에이전트는 HTTP 서버와 Kafka Consumer를 모두 실행합니다:

```python
if __name__ == "__main__":
    # 1. Kafka 레지스트리에 등록
    asyncio.run(register_agent("data", agent_card))
    
    # 2. Kafka Consumer 시작 (백그라운드)
    kafka_thread = threading.Thread(target=run_kafka_consumer, daemon=True)
    kafka_thread.start()
    
    # 3. HTTP 서버 시작
    uvicorn.run(app, host="127.0.0.1", port=9003)
```

### 4단계: 테스트

멀티턴 대화를 테스트합니다:

```python
async def test_multiturn():
    transport = KafkaTransport(target_agent_name="data")
    
    # 1턴: 모호한 질문
    result1 = await transport.send_message(
        MessageSendParams(message=Message(text="승률?"))
    )
    print(f"응답: {result1.status.state}")  # input-required
    
    # 2턴: 명확화 제공
    result2 = await transport.send_message(
        MessageSendParams(message=Message(
            text="저그",
            context_id=result1.context_id
        ))
    )
    print(f"최종 결과: {result2.artifacts[0].text}")  # 저그 승률 50%
```

## AWS 서비스 통합

### Amazon MSK: 프로덕션 Kafka

로컬 개발에서는 Docker로 Kafka를 실행하지만, 프로덕션에서는 Amazon MSK를 사용합니다.

**MSK의 장점:**
- **관리 부담 감소**: 브로커 프로비저닝, 패치, 모니터링을 AWS가 담당
- **고가용성**: 3개 가용 영역에 자동 복제
- **보안**: VPC 격리, 전송 중/저장 시 암호화, IAM 인증
- **확장성**: 브로커 추가나 스토리지 확장이 간단

**권장 구성:**

| 환경 | 인스턴스 | 브로커 수 | 스토리지 | 월 비용 |
|------|---------|----------|---------|---------|
| 개발/테스트 | kafka.t3.small | 3 | 100GB | ~$200 |
| 프로덕션 | kafka.m5.large | 3-6 | 1TB GP3 | ~$1,500 |

**MSK 연결 설정:**

```python
# MSK 엔드포인트로 변경
transport = KafkaTransport(
    target_agent_name="data",
    bootstrap_servers="b-1.gamebalance.xxx.kafka.us-east-1.amazonaws.com:9094"
)
```

### Amazon Bedrock: LLM 통합

각 에이전트는 Amazon Bedrock의 foundation model을 사용합니다.

**모델 선택 가이드:**

| 모델 | 특징 | 적합한 용도 | 비용 |
|------|------|------------|------|
| Nova Lite | 빠르고 저렴 | 단순 분류, 빠른 응답 | 낮음 |
| Claude 3 Haiku | 균형잡힌 성능 | 일반적인 대화 | 중간 |
| Claude 3 Sonnet | 높은 추론 능력 | 복잡한 분석, 종합 | 높음 |

우리 시스템에서는:
- **Data Agent**: Nova Lite (통계 조회는 단순)
- **CS Agent**: Claude 3 Haiku (텍스트 분석)
- **Balance Agent**: Claude 3 Sonnet (종합 판단)

```python
# 에이전트별로 적절한 모델 선택
model = BedrockModel(
    model_id="anthropic.claude-3-sonnet-20240229-v1:0",
    region="us-east-1",
    model_kwargs={"temperature": 0.7, "max_tokens": 4096}
)
```

### CloudWatch: 관찰성

분산 시스템에서 관찰성은 필수입니다. 우리는 세 가지 수준의 모니터링을 구현했습니다:

**메트릭 수집:**
- 에이전트별 요청 수, 응답 시간, 에러율
- Kafka 토픽별 메시지 처리량, 지연시간
- Bedrock 토큰 사용량 (비용 추적)

**로그 통합:**
- 모든 에이전트의 로그를 CloudWatch Logs로 중앙 집중
- Correlation ID와 Context ID를 로그에 포함하여 추적 가능

```python
logger.info("Request received", extra={
    "agent_name": "balance",
    "correlation_id": correlation_id,
    "context_id": context_id
})
```

**분산 추적:**
- AWS X-Ray로 요청의 전체 흐름 시각화
- 어떤 에이전트가 어떤 에이전트를 호출했는지 한눈에 파악

## 성능과 확장성

### 벤치마크 결과

로컬 Kafka와 Amazon MSK에서 성능을 측정했습니다:

| 메트릭 | 로컬 Kafka | Amazon MSK |
|--------|-----------|------------|
| 처리량 | 1,000 msg/s | 10,000+ msg/s |
| 평균 지연시간 | 50ms | 80ms |
| P99 지연시간 | 200ms | 300ms |
| 메시지 내구성 | 단일 브로커 | 3개 AZ 복제 |

MSK가 약간 더 높은 지연시간을 보이지만, 이는 네트워크 거리 때문이며 안정성과 확장성을 고려하면 충분히 수용 가능한 수준입니다.

### 확장 전략

**수평 확장:**

각 에이전트는 Consumer Group을 사용하여 여러 인스턴스를 실행할 수 있습니다:

```python
# 같은 group_id를 사용하면 Kafka가 자동으로 로드 밸런싱
consumer = AIOKafkaConsumer(
    'agent.data.requests',
    group_id='data-agent-group',  # 여러 인스턴스가 공유
    bootstrap_servers=MSK_CONFIG['bootstrap_servers']
)
```

예: Data Agent를 3개 인스턴스로 실행하면, 각 인스턴스가 요청의 1/3씩 처리합니다.

**수직 확장:**

트래픽이 많은 에이전트의 토픽은 파티션 수를 늘려 병렬 처리를 증가시킵니다.

### 비용 최적화

**MSK 비용:**
- 브로커 인스턴스 비용이 대부분
- GP3 스토리지 사용으로 비용 절감
- 트래픽이 적은 시간대에는 브로커 수 감소 고려

**Bedrock 비용:**
- 토큰 사용량에 따라 과금
- 간단한 작업은 저렴한 모델 사용
- 프롬프트 캐싱으로 반복 비용 절감

```python
# 작업 복잡도에 따라 모델 선택
def get_model_for_task(complexity: str):
    if complexity == "simple":
        return BedrockModel(model_id="amazon.nova-lite-v1:0")
    elif complexity == "medium":
        return BedrockModel(model_id="anthropic.claude-3-haiku-20240307-v1:0")
    else:
        return BedrockModel(model_id="anthropic.claude-3-sonnet-20240229-v1:0")
```

## 실전 활용 패턴

### 순차 실행 패턴

여러 에이전트를 순서대로 호출하여 파이프라인 구성:

```python
async def sequential_analysis(query: str):
    # 1. 데이터 분석
    data_result = await call_agent("data", f"통계 분석: {query}")
    
    # 2. CS 피드백 분석 (데이터 결과 활용)
    cs_result = await call_agent("cs", f"다음 데이터에 대한 유저 피드백: {data_result}")
    
    # 3. 종합 분석
    return await call_agent("balance", f"데이터: {data_result}\n피드백: {cs_result}\n종합 제안")
```

**장점:** 각 단계의 결과가 다음 단계의 입력이 되어 점진적으로 정보 축적

### 병렬 실행 패턴

여러 에이전트를 동시에 호출하여 시간 단축:

```python
async def parallel_analysis(query: str):
    # 동시에 여러 에이전트 호출
    data_task = call_agent("data", f"통계 분석: {query}")
    cs_task = call_agent("cs", f"피드백 분석: {query}")
    
    # 모든 결과 대기
    data_result, cs_result = await asyncio.gather(data_task, cs_task)
    
    return {"data": data_result, "feedback": cs_result}
```

**장점:** 전체 처리 시간이 가장 느린 에이전트의 시간으로 단축

### 조건부 실행 패턴

첫 번째 에이전트의 결과에 따라 다음 행동 결정:

```python
async def conditional_analysis(query: str):
    # 먼저 간단한 분석
    initial_result = await call_agent("data", query)
    
    # 결과에 따라 추가 분석 결정
    if "이상" in initial_result or "문제" in initial_result:
        # 문제가 발견되면 CS 피드백도 확인
        cs_result = await call_agent("cs", f"다음 이슈에 대한 컴플레인: {query}")
        return f"{initial_result}\n\n추가 분석:\n{cs_result}"
    
    return initial_result
```

**장점:** 불필요한 호출을 줄여 비용과 시간 절약

## 다른 도메인으로의 확장

이 아키텍처는 게임 밸런스 외에도 다양한 분야에 적용 가능합니다:

### 고객 지원 자동화

```
Ticket Agent (분류) → Knowledge Agent (검색) → Resolution Agent (해결책)
```

- 고객 문의를 자동으로 분류
- 지식베이스에서 관련 정보 검색
- 맞춤형 해결책 생성

### 금융 리스크 분석

```
Market Agent (시장 분석) ┐
Risk Agent (리스크 평가)  ├→ 병렬 실행 → 종합 보고서
Compliance Agent (규정)  ┘
```

- 시장 데이터, 리스크, 규정 준수를 동시에 분석
- 포트폴리오에 대한 종합적인 평가 제공

### 콘텐츠 생성 파이프라인

```
Research Agent → Writer Agent → Editor Agent
```

- 주제 조사 → 초안 작성 → 편집 및 개선
- 각 단계가 이전 단계의 결과를 활용

## 모범 사례와 교훈

### 설계 원칙

**느슨한 결합:**
에이전트는 서로의 구현을 알 필요 없이 메시지만 교환합니다. 한 에이전트를 변경해도 다른 에이전트에 영향이 없습니다.

**단일 책임:**
각 에이전트는 하나의 명확한 역할만 수행합니다. Data Agent는 데이터만, CS Agent는 피드백만 담당합니다.

**멱등성:**
같은 요청을 여러 번 처리해도 같은 결과가 나와야 합니다. 네트워크 문제로 재시도가 발생해도 안전합니다.

### 운영 교훈

**타임아웃의 중요성:**

모든 에이전트 호출에 적절한 타임아웃을 설정해야 합니다:

```python
# 타임아웃 설정으로 무한 대기 방지
response = await asyncio.wait_for(
    transport.send_message(request),
    timeout=40.0
)
```

**점진적 롤아웃:**

새로운 에이전트나 기능은 작은 트래픽부터 시작하여 점진적으로 확대합니다. 문제 발생 시 빠르게 롤백할 수 있습니다.

**관찰성 우선:**

처음부터 로깅, 메트릭, 추적을 구현해야 합니다. 문제가 발생한 후에 추가하기는 어렵습니다.

### 에러 처리 전략

**재시도 로직:**

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def send_with_retry(transport, message):
    return await transport.send_message(MessageSendParams(message=message))
```

**서킷 브레이커:**

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def call_agent_with_circuit_breaker(agent_id: str, query: str):
    transport = get_transport(agent_id)
    return await transport.send_message(create_message(query))
```

## 결론

A2A 프로토콜과 Kafka의 결합은 분산 AI 에이전트 시스템의 새로운 가능성을 열어줍니다. 이 아키텍처는:

**확장성:** 에이전트를 추가하거나 인스턴스를 늘리는 것이 간단합니다. N개의 에이전트가 있어도 N+M개의 연결만 관리하면 됩니다.

**안정성:** 한 에이전트의 장애가 다른 에이전트에 영향을 주지 않습니다. Kafka의 메시지 영속성으로 메시지 손실도 방지합니다.

**관찰성:** 모든 상호작용이 Kafka를 통과하므로 중앙에서 추적하고 분석할 수 있습니다.

**유연성:** 순차, 병렬, 조건부 등 다양한 실행 패턴을 지원합니다.

### 핵심 성과

이 프로젝트를 통해 다음을 달성했습니다:

1. **A2A 프로토콜의 완전한 Kafka 구현**: HTTP 없이도 모든 A2A 기능 지원
2. **확장 가능한 아키텍처**: Hub-Spoke 패턴으로 선형 확장성 확보
3. **프로덕션 준비**: MSK, Bedrock, CloudWatch 통합으로 엔터프라이즈급 시스템 구축
4. **실용적 검증**: 게임 밸런스 자동화라는 실제 사용 사례로 검증

### 향후 방향

**스키마 레지스트리 통합:**
메시지 형식의 버전 관리로 호환성 보장

**멀티 리전 배포:**
글로벌 서비스를 위한 지역 간 복제

```
Region 1 (us-east-1)          Region 2 (eu-west-1)
┌─────────────────┐          ┌─────────────────┐
│   MSK Cluster   │◄────────►│   MSK Cluster   │
│   + Agents      │  Mirror  │   + Agents      │
└─────────────────┘  Maker   └─────────────────┘
```

**고급 라우팅:**
우선순위, 배치 처리 등 더 정교한 메시지 흐름

**오케스트레이션 DSL:**
복잡한 워크플로우를 선언적으로 정의

이 글에서 소개한 패턴과 경험이 여러분의 AI 에이전트 시스템 구축에 도움이 되기를 바랍니다. 소스 코드와 추가 예제는 [GitHub 저장소](https://github.com/aws-samples/msk-a2a-demo)에서 확인하실 수 있습니다.

---

## 참고 자료

- [Google A2A 프로토콜 발표](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)
- [A2A 프로토콜 사양](https://github.com/google/agent-to-agent)
- [Amazon MSK 개발자 가이드](https://docs.aws.amazon.com/msk/)
- [Amazon Bedrock 사용자 가이드](https://docs.aws.amazon.com/bedrock/)
- [Strands Agents SDK](https://strandsagents.com/)
- [Apache Kafka 문서](https://kafka.apache.org/documentation/)

## 저자 소개

질문이나 피드백이 있으시면 댓글로 남겨주세요!


