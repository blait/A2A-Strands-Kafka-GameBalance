# HTTP vs Kafka 로직 비교

## 현재 HTTP 방식 로직

### 1. 초기화 단계 (Balance Agent 시작 시)

```python
class A2AClient:
    async def init(self):
        # Step 1: HTTP URL로 연결
        async with httpx.AsyncClient(timeout=60) as client:
            for name, url in self.agents.items():
                # Step 2: AgentCard 조회 (GET /card)
                resolver = A2ACardResolver(httpx_client=client, base_url=url)
                card = await resolver.get_agent_card()
                
                # Step 3: Card에서 정보 추출
                # - name: "Data Analysis Agent"
                # - skills: [analyze_game_stats, ...]
                # - capabilities: {streaming: true, multi_turn: true}
                # - url: "http://localhost:9003"
                
                self.cards[name] = card
                print(f"✅ Connected to {name} agent")
```

**흐름:**
```
Balance Agent 시작
    ↓
1. HTTP GET http://localhost:9003/card
    ↓
2. AgentCard 응답 받음
    {
      "name": "Data Analysis Agent",
      "url": "http://localhost:9003",
      "skills": [...],
      "capabilities": {...}
    }
    ↓
3. Card 저장 (메모리)
    ↓
4. HTTP GET http://localhost:9002/card (CS Agent)
    ↓
5. 준비 완료
```

### 2. 요청 단계 (에이전트 호출 시)

```python
async def call_agent(self, agent_name: str, query: str):
    # Step 1: 저장된 Card 조회
    card = self.cards[agent_name]
    
    # Step 2: HTTP Client 생성
    async with httpx.AsyncClient(timeout=60) as client:
        config = ClientConfig(httpx_client=client, streaming=False)
        factory = ClientFactory(config)
        
        # Step 3: A2A Client 생성 (Card 기반)
        a2a_client = factory.create(card)
        
        # Step 4: 메시지 생성
        msg = Message(
            role=Role.user,
            parts=[TextPart(text=query)],
            message_id=uuid4().hex
        )
        
        # Step 5: HTTP POST 요청
        # POST http://localhost:9003/v1/message:send
        result = await a2a_client.send_message(msg)
        
        # Step 6: 응답 파싱
        return result.artifacts[0].parts[0].text
```

**흐름:**
```
call_agent("data", "테란 승률?")
    ↓
1. Card 조회 (메모리)
    ↓
2. HTTP Client 생성
    ↓
3. A2A Client 생성
    ↓
4. HTTP POST http://localhost:9003/v1/message:send
   Body: {
     "message": {
       "role": "user",
       "parts": [{"text": "테란 승률?"}]
     }
   }
    ↓
5. Data Agent 처리 (2초)
    ↓
6. HTTP Response
   {
     "task": {
       "artifacts": [{"parts": [{"text": "테란 승률 58%"}]}]
     }
   }
    ↓
7. 응답 반환
```

---

## Kafka 방식 로직

### 1. 초기화 단계 (Balance Agent 시작 시)

```python
class A2AClient:
    async def init(self):
        # Step 1: Kafka Transport 생성 (URL 불필요!)
        for name in self.agents.keys():
            self.transports[name] = KafkaTransport(
                target_agent_name=name,  # "data", "cs"
                bootstrap_servers="localhost:9092"
            )
            
            # Step 2: Kafka Producer/Consumer 시작
            # - Producer: agent.data.requests topic에 발행
            # - Consumer: agent.data.responses topic 구독
            
            print(f"✅ Kafka transport ready for {name} agent")
```

**흐름:**
```
Balance Agent 시작
    ↓
1. KafkaTransport("data") 생성
    ↓
2. Kafka Producer 시작
   - 연결: localhost:9092
   - 발행 topic: agent.data.requests
    ↓
3. Kafka Consumer 시작
   - 연결: localhost:9092
   - 구독 topic: agent.data.responses
   - Group ID: client-abc123
    ↓
4. 백그라운드 Consumer 실행
   (응답 대기)
    ↓
5. KafkaTransport("cs") 생성 (동일)
    ↓
6. 준비 완료 (AgentCard 조회 없음!)
```

**차이점:**
- ❌ HTTP 연결 불필요
- ❌ AgentCard 조회 불필요
- ❌ URL 불필요
- ✅ Kafka만 연결
- ✅ Agent 이름만 알면 됨

### 2. 요청 단계 (에이전트 호출 시)

```python
async def call_agent(self, agent_name: str, query: str):
    # Step 1: Transport 조회
    transport = self.transports[agent_name]
    
    # Step 2: 메시지 생성 (동일)
    msg = Message(
        role=Role.user,
        parts=[TextPart(text=query)],
        message_id=uuid4().hex
    )
    
    # Step 3: Kafka로 발행
    result = await transport.send_message(
        MessageSendParams(message=msg)
    )
    
    # Step 4: 응답 반환
    return result.artifacts[0].parts[0].text
```

**흐름:**
```
call_agent("data", "테란 승률?")
    ↓
1. Transport 조회 (메모리)
    ↓
2. Correlation ID 생성: "abc-123"
    ↓
3. Kafka Produce
   Topic: agent.data.requests
   Key: "abc-123"
   Value: {
     "method": "send_message",
     "params": {
       "message": {
         "role": "user",
         "parts": [{"text": "테란 승률?"}]
       }
     }
   }
    ↓
4. Kafka에 저장 (디스크)
    ↓
5. Data Agent가 Consume
    ↓
6. Data Agent 처리 (2초)
    ↓
7. Data Agent가 Produce
   Topic: agent.data.responses
   Key: "abc-123"
   Value: {
     "task_id": "...",
     "artifacts": [{"parts": [{"text": "테란 승률 58%"}]}]
   }
    ↓
8. Balance Agent Consumer가 수신
   (Correlation ID 매칭: "abc-123")
    ↓
9. 응답 Queue에 저장
    ↓
10. send_message() 함수가 응답 반환
```

---

## 핵심 차이점

### Discovery & AgentCard

#### HTTP 방식
```python
# 1. URL 필요
url = "http://localhost:9003"

# 2. AgentCard 조회 필요
GET /card
→ {name, skills, capabilities, url}

# 3. Card 기반으로 Client 생성
factory.create(card)
```

#### Kafka 방식
```python
# 1. Agent 이름만 필요
agent_name = "data"

# 2. AgentCard 조회 불필요!
# (선택사항: 정적 Card 사용 가능)

# 3. Transport 직접 생성
KafkaTransport(target_agent_name="data")
```

**왜 Card가 불필요?**
- Kafka Topic 이름이 곧 주소
- `agent.data.requests` → Data Agent
- `agent.cs.requests` → CS Agent
- URL, 포트 정보 불필요

### Skill & Tool 정보

#### HTTP 방식
```python
# AgentCard에서 Skill 확인
card.skills = [
    {
        "id": "analyze_game_stats",
        "name": "analyze_game_stats",
        "description": "게임 통계 분석"
    }
]

# Tool 정보도 Card에 포함 가능
```

#### Kafka 방식
```python
# Option 1: AgentCard 여전히 사용 가능
transport = KafkaTransport(
    target_agent_name="data",
    agent_card=static_card  # 정적 Card
)

# Option 2: Card 없이 사용
# - Skill 정보 불필요
# - 단순히 메시지만 전달
transport = KafkaTransport(target_agent_name="data")
```

**차이점:**
- HTTP: Card 필수 (URL 포함)
- Kafka: Card 선택사항 (메타데이터용)

### 연결 확인

#### HTTP 방식
```python
# 초기화 시 연결 확인
try:
    card = await resolver.get_agent_card()
    print("✅ Connected")
except:
    print("❌ Failed to connect")
```

#### Kafka 방식
```python
# 초기화 시 연결 확인 불필요
# Kafka만 연결되면 OK
await producer.start()
print("✅ Kafka transport ready")

# Agent가 실제로 살아있는지는
# 첫 요청 시 확인
```

**차이점:**
- HTTP: 사전 연결 확인 (Health Check)
- Kafka: 지연 확인 (첫 요청 시)

---

## 상세 비교표

| 단계 | HTTP | Kafka |
|------|------|-------|
| **Discovery** | HTTP GET /card | Topic 이름 규칙 |
| **AgentCard** | 필수 (URL 포함) | 선택사항 |
| **Skill 정보** | Card에서 조회 | 정적 정의 or Card |
| **URL/주소** | http://host:port | agent.{name}.requests |
| **연결 확인** | 초기화 시 확인 | 지연 확인 |
| **요청 전송** | HTTP POST | Kafka Produce |
| **응답 수신** | HTTP Response | Kafka Consume |
| **Correlation** | HTTP 세션 | Correlation ID |

---

## 실제 코드 비교

### HTTP 초기화
```python
# 복잡함
async def init(self):
    async with httpx.AsyncClient(timeout=60) as client:
        for name, url in self.agents.items():
            try:
                resolver = A2ACardResolver(
                    httpx_client=client, 
                    base_url=url
                )
                card = await resolver.get_agent_card()
                self.cards[name] = card
                print(f"✅ Connected to {name}")
            except Exception as e:
                print(f"❌ Failed: {e}")
```

### Kafka 초기화
```python
# 간단함
async def init(self):
    for name in ["data", "cs"]:
        self.transports[name] = KafkaTransport(
            target_agent_name=name,
            bootstrap_servers="localhost:9092"
        )
        print(f"✅ Kafka transport ready for {name}")
```

### HTTP 호출
```python
# 복잡함
async def call_agent(self, agent_name: str, query: str):
    card = self.cards[agent_name]
    async with httpx.AsyncClient(timeout=60) as client:
        config = ClientConfig(httpx_client=client)
        factory = ClientFactory(config)
        a2a_client = factory.create(card)
        msg = Message(...)
        result = await a2a_client.send_message(msg)
        return result.artifacts[0].parts[0].text
```

### Kafka 호출
```python
# 간단함
async def call_agent(self, agent_name: str, query: str):
    transport = self.transports[agent_name]
    msg = Message(...)
    result = await transport.send_message(
        MessageSendParams(message=msg)
    )
    return result.artifacts[0].parts[0].text
```

---

## AgentCard는 어떻게 되나?

### Option 1: 정적 Card 사용
```python
# 코드에 하드코딩
DATA_AGENT_CARD = AgentCard(
    name="Data Analysis Agent",
    description="게임 통계 분석",
    skills=[...],
    capabilities={...}
)

transport = KafkaTransport(
    target_agent_name="data",
    agent_card=DATA_AGENT_CARD
)
```

### Option 2: Kafka로 Card 조회
```python
# 별도 topic으로 Card 조회
# Topic: agent.cards
# Key: "data"
# Value: {name, skills, capabilities}

card = await kafka_get_card("data")
transport = KafkaTransport(
    target_agent_name="data",
    agent_card=card
)
```

### Option 3: Card 없이 사용
```python
# Card 정보 불필요한 경우
transport = KafkaTransport(target_agent_name="data")
# 단순히 메시지만 전달
```

---

## 추천 방식

### 이 프로젝트에서는?

**Option 1 + Option 3 혼합:**

```python
class A2AClient:
    def __init__(self):
        # 정적 Card 정의 (메타데이터용)
        self.agent_info = {
            "data": {
                "name": "Data Analysis Agent",
                "description": "게임 통계 분석"
            },
            "cs": {
                "name": "CS Feedback Agent",
                "description": "유저 피드백 분석"
            }
        }
    
    async def init(self):
        # Kafka Transport만 생성 (Card 불필요)
        for name in self.agent_info.keys():
            self.transports[name] = KafkaTransport(
                target_agent_name=name,
                bootstrap_servers="localhost:9092"
            )
```

**장점:**
- 간단함
- AgentCard 조회 불필요
- 메타데이터는 코드에 정의
- Kafka만 연결하면 작동

---

## 결론

### HTTP 로직
```
Discovery → Card 조회 → Skill 확인 → URL 저장 → HTTP 연결
```

### Kafka 로직
```
Agent 이름 → Kafka Transport 생성 → 완료
```

**Kafka가 훨씬 간단해요!**
