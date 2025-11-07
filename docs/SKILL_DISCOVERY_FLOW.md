# Skill Discovery Flow - Agent가 Skill을 알게 되는 과정

## 전체 흐름 요약

```
1. Data/CS Agent 시작
   └─> AgentCard 정의 (Skill 포함)
   └─> agent.cards topic에 발행

2. Balance Agent 시작
   └─> agent.cards topic 구독
   └─> 모든 AgentCard 수집
   └─> Skill 정보 추출
   └─> Tool 동적 생성
   └─> Strands Agent에 등록

3. LLM이 Tool 사용
   └─> Skill 자동 호출
```

---

## 1단계: Server Agent가 Skill 정의

### Data Analysis Agent 예시

**파일**: `agents/data_analysis_agent.py`

```python
# AgentCard 정의
agent_card = AgentCard(
    name="Data Analysis Agent",
    description="게임 통계 데이터 분석 전문 에이전트",
    skills=[
        Skill(
            id="analyze_game_stats",
            name="analyze_game_stats",
            description="게임 로그를 분석하여 종족별 승률, 픽률, 밸런스 문제를 파악합니다."
        )
    ],
    capabilities=AgentCapabilities(
        streaming=True,
        multi_turn=True
    )
)
```

**Skill 구조:**
- `id`: 고유 식별자
- `name`: Tool 함수 이름으로 사용됨
- `description`: LLM이 언제 이 Tool을 사용할지 판단하는 기준

---

## 2단계: AgentCard를 Kafka에 발행

### agent.cards Topic에 발행

**파일**: `kafka/agent_registry.py`

```python
async def publish_agent_card(
    agent_id: str,
    card: dict,
    bootstrap_servers: str = "localhost:9092"
):
    """에이전트 시작 시 AgentCard 발행"""
    
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode()
    )
    await producer.start()
    
    try:
        # Kafka에 Card 발행
        await producer.send(
            "agent.cards",
            key=agent_id.encode(),  # Key: "data"
            value={
                "name": "Data Analysis Agent",
                "description": "게임 통계 데이터 분석",
                "skills": [
                    {
                        "id": "analyze_game_stats",
                        "name": "analyze_game_stats",
                        "description": "게임 로그 분석"
                    }
                ]
            }
        )
        print(f"✅ Published AgentCard for {agent_id}")
    finally:
        await producer.stop()
```

**Kafka 메시지:**
```
Topic: agent.cards
Key: "data"
Value: {
  "name": "Data Analysis Agent",
  "skills": [
    {
      "name": "analyze_game_stats",
      "description": "게임 로그 분석"
    }
  ]
}
```

---

## 3단계: Balance Agent가 AgentCard 수집

### agent.cards Topic 구독

**파일**: `kafka/agent_registry.py`

```python
async def discover_agents(bootstrap_servers: str = "localhost:9092") -> dict:
    """agent.cards topic에서 모든 AgentCard 수집"""
    
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
        # 모든 메시지 읽기
        async for msg in consumer:
            agent_id = msg.key.decode()  # "data"
            card_data = msg.value
            
            # Card 저장
            agent_cards[agent_id] = card_data
            
            print(f"📥 Discovered agent: {agent_id}")
            print(f"   Skills: {[s['name'] for s in card_data.get('skills', [])]}")
            
            # 모든 메시지 읽었으면 종료
            if consumer.highwater(msg.partition) == msg.offset + 1:
                break
    finally:
        await consumer.stop()
    
    return agent_cards
```

**결과:**
```python
agent_cards = {
    "data": {
        "name": "Data Analysis Agent",
        "skills": [
            {"name": "analyze_game_stats", "description": "게임 로그 분석"}
        ]
    },
    "cs": {
        "name": "CS Feedback Agent",
        "skills": [
            {"name": "analyze_feedback", "description": "유저 피드백 분석"}
        ]
    }
}
```

---

## 4단계: Skill을 Tool로 변환

### Tool 동적 생성

**파일**: `agents/game_balance_agent_executor.py`

```python
def create_agent_tool(agent_id: str, skill_name: str, description: str):
    """Skill을 Strands Tool로 변환"""
    
    async def delegation_function(query: str) -> str:
        """실제 Tool 함수 - LLM이 호출"""
        
        # 1. KafkaTransport 가져오기
        transport = a2a_client.get_transport(agent_id)
        
        # 2. 메시지 생성
        msg = Message(
            kind="message",
            role=Role.user,
            parts=[Part(TextPart(kind="text", text=query))],
            message_id=uuid4().hex
        )
        
        # 3. Kafka로 요청 전송
        response_text = ""
        async for event in transport.send_message_streaming(
            MessageSendParams(message=msg)
        ):
            if hasattr(event, 'artifact') and event.artifact:
                for part in event.artifact.parts:
                    if hasattr(part, 'text'):
                        response_text += part.text
        
        return response_text
    
    # Tool 메타데이터 설정
    delegation_function.__name__ = skill_name  # "analyze_game_stats"
    delegation_function.__doc__ = description  # "게임 로그 분석"
    
    return tool(delegation_function)
```

**변환 과정:**
```
Skill:
  name: "analyze_game_stats"
  description: "게임 로그 분석"

↓ 변환

Tool Function:
  함수명: analyze_game_stats
  docstring: "게임 로그 분석"
  실행: Kafka로 Data Agent 호출
```

---

## 5단계: Agent 생성 시 Tool 등록

### Strands Agent에 Tool 등록

**파일**: `agents/game_balance_agent_executor.py`

```python
async def create_agent():
    """Balance Agent 생성"""
    
    # 1. AgentCard 수집
    await a2a_client.init()
    
    print(f"\n🔍 [Balance Agent] Discovered Agents:")
    for agent_id, card in a2a_client.agent_cards.items():
        print(f"  - {agent_id}: {card['name']}")
        for skill in card.get('skills', []):
            print(f"    Skill: {skill['name']} - {skill['description']}")
    
    # 2. Tool 생성
    tools = []
    for agent_id, card in a2a_client.agent_cards.items():
        if agent_id == "balance":  # 자기 자신 제외
            continue
        
        # 각 Skill을 Tool로 변환
        for skill in card.get('skills', []):
            skill_name = skill['name']
            skill_desc = skill['description']
            
            # Tool 생성
            tool_func = create_agent_tool(agent_id, skill_name, skill_desc)
            tools.append(tool_func)
            
            print(f"✅ Created tool: {skill_name} (calls {agent_id})")
    
    # 3. Strands Agent 생성
    return Agent(
        name="Game Balance Agent",
        model=BedrockModel(model_id="us.amazon.nova-lite-v1:0"),
        tools=tools,  # Tool 등록
        system_prompt=f"""당신은 게임 밸런스 조정 담당자입니다.

**사용 가능한 도구:**
- analyze_game_stats: 게임 로그 분석
- analyze_feedback: 유저 피드백 분석

**중요: 사용자 요청에 맞는 도구를 사용하세요.**"""
    )
```

**실행 로그:**
```
🔍 [Balance Agent] Discovered Agents:
  - data: Data Analysis Agent
    Skill: analyze_game_stats - 게임 로그 분석
  - cs: CS Feedback Agent
    Skill: analyze_feedback - 유저 피드백 분석

✅ Created tool: analyze_game_stats (calls data)
✅ Created tool: analyze_feedback (calls cs)
```

---

## 6단계: LLM이 Tool 사용

### 사용자 요청 처리

**사용자 입력:**
```
"테란과 저그의 밸런스를 분석해줘"
```

**LLM의 판단:**
```
1. system_prompt 확인
   - "analyze_game_stats: 게임 로그 분석" 발견

2. Tool 선택
   - 게임 밸런스 분석 → analyze_game_stats 호출 필요

3. Tool 호출
   analyze_game_stats("테란과 저그의 승률을 분석해줘")
```

**Tool 실행:**
```python
# delegation_function 실행
async def delegation_function(query: str) -> str:
    # Kafka로 Data Agent 호출
    transport = a2a_client.get_transport("data")
    
    # 메시지 전송
    msg = Message(text="테란과 저그의 승률을 분석해줘")
    response = await transport.send_message_streaming(msg)
    
    # 응답 수집
    return "테란 승률 58%, 저그 42%"
```

**LLM의 최종 응답:**
```
분석 결과:
- 테란 승률: 58%
- 저그 승률: 42%

테란이 강한 것으로 보입니다. 저그 버프가 필요합니다.
```

---

## 전체 데이터 흐름

### 시퀀스 다이어그램

```
Data Agent                 Kafka                  Balance Agent              LLM
    |                        |                          |                      |
    | 1. Publish Card        |                          |                      |
    |----------------------->|                          |                      |
    |   Key: "data"          |                          |                      |
    |   Skills: [...]        |                          |                      |
    |                        |                          |                      |
    |                        | 2. Subscribe agent.cards |                      |
    |                        |<-------------------------|                      |
    |                        |                          |                      |
    |                        | 3. Consume Cards         |                      |
    |                        |------------------------->|                      |
    |                        |   {data: {...}}          |                      |
    |                        |                          |                      |
    |                        |                          | 4. Create Tools      |
    |                        |                          |--------------------->|
    |                        |                          |   analyze_game_stats |
    |                        |                          |                      |
    |                        |                          | 5. User Request      |
    |                        |                          |<---------------------|
    |                        |                          |   "밸런스 분석"      |
    |                        |                          |                      |
    |                        |                          | 6. LLM decides       |
    |                        |                          |--------------------->|
    |                        |                          |   Call Tool          |
    |                        |                          |                      |
    |                        | 7. Kafka Request         |                      |
    |                        |<-------------------------|                      |
    |                        |   agent.data.requests    |                      |
    |                        |                          |                      |
    | 8. Process             |                          |                      |
    |<-----------------------|                          |                      |
    |                        |                          |                      |
    | 9. Kafka Response      |                          |                      |
    |----------------------->|                          |                      |
    |   agent.data.responses |                          |                      |
    |                        |                          |                      |
    |                        | 10. Tool Result          |                      |
    |                        |------------------------->|                      |
    |                        |   "테란 58%, 저그 42%"   |                      |
    |                        |                          |                      |
    |                        |                          | 11. Final Answer     |
    |                        |                          |--------------------->|
    |                        |                          |   "테란이 강함"      |
```

---

## 핵심 포인트

### 1. AgentCard = Skill 명세서
- 각 Agent가 제공하는 기능(Skill) 정의
- Kafka에 발행하여 다른 Agent가 발견 가능

### 2. agent.cards = 중앙 레지스트리
- Compacted Topic으로 최신 Card만 유지
- 모든 Agent의 Skill 정보 저장
- Balance Agent가 구독하여 수집

### 3. Skill → Tool 변환
- Skill 정보를 Strands Tool로 변환
- Tool 함수는 Kafka로 해당 Agent 호출
- LLM이 자동으로 적절한 Tool 선택

### 4. 동적 Discovery
- 새 Agent 추가 시: Card만 발행하면 자동 발견
- Balance Agent 재시작 시: 모든 Skill 자동 로드
- URL이나 설정 파일 불필요

---

## 코드 위치 요약

| 단계 | 파일 | 함수/클래스 |
|------|------|------------|
| 1. Skill 정의 | `agents/data_analysis_agent.py` | `agent_card` |
| 2. Card 발행 | `kafka/agent_registry.py` | `publish_agent_card()` |
| 3. Card 수집 | `kafka/agent_registry.py` | `discover_agents()` |
| 4. Tool 생성 | `agents/game_balance_agent_executor.py` | `create_agent_tool()` |
| 5. Agent 생성 | `agents/game_balance_agent_executor.py` | `create_agent()` |
| 6. Tool 실행 | `agents/game_balance_agent_executor.py` | `delegation_function()` |

---

## 예시: 새 Agent 추가

### Weather Agent 추가하기

**1. Weather Agent 생성**
```python
# agents/weather_agent.py

agent_card = AgentCard(
    name="Weather Agent",
    skills=[
        Skill(
            name="get_weather",
            description="특정 지역의 날씨 정보를 조회합니다"
        )
    ]
)

# Kafka에 Card 발행
await publish_agent_card("weather", agent_card)
```

**2. Balance Agent 재시작**
```bash
./restart_all.sh
```

**3. 자동으로 Tool 생성됨**
```
🔍 [Balance Agent] Discovered Agents:
  - data: Data Analysis Agent
  - cs: CS Feedback Agent
  - weather: Weather Agent  ← 새로 추가됨!
    Skill: get_weather - 날씨 정보 조회

✅ Created tool: get_weather (calls weather)
```

**4. LLM이 자동으로 사용**
```
사용자: "서울 날씨 알려줘"
LLM: get_weather("서울") 호출
응답: "서울 날씨: 맑음, 25도"
```

**추가 설정 불필요!**
- URL 설정 ❌
- 코드 수정 ❌
- 설정 파일 ❌
- Card 발행만 하면 끝 ✅

---

## 장점

### 1. 자동 Discovery
- 새 Agent 추가 시 자동 발견
- 수동 설정 불필요

### 2. 중앙 집중식 관리
- agent.cards에 모든 Skill 정보
- 한 곳에서 관리

### 3. 동적 Tool 생성
- Skill 정보로 Tool 자동 생성
- LLM이 자동으로 사용

### 4. 확장 가능
- N개 Agent 추가 가능
- 선형 증가 (N+M)

### 5. 느슨한 결합
- Agent 간 직접 의존성 없음
- Kafka만 연결
