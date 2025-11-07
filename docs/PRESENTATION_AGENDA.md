# A2A + Kafka 구현 발표 아젠다

## 발표 개요
- **주제**: Google A2A 프로토콜을 Kafka로 구현한 멀티 에이전트 시스템
- **목표**: HTTP 대신 Kafka를 사용하여 확장 가능한 에이전트 통신 구현
- **시간**: 20-30분

---

## 1. 문제 정의 (3분)

### 1.1 기존 HTTP 방식의 한계
- **N² 연결 문제**: 에이전트 N개 → N×(N-1) 연결 필요
- **URL 관리**: 각 에이전트의 주소를 알아야 함
- **장애 전파**: 한 에이전트 다운 시 연결된 모든 에이전트 영향
- **메시지 손실**: HTTP는 영속성 없음

### 1.2 왜 Kafka인가?
- **Hub-Spoke 구조**: N² → N+M 연결 (선형 증가)
- **메시지 영속성**: 모든 통신 기록 저장
- **느슨한 결합**: URL 불필요, 장애 격리
- **확장성**: 에이전트 추가 시 Kafka만 연결

---

## 2. 아키텍처 소개 (5분)

### 2.1 Hub-Spoke 구조
```
Balance Agent (Client)
    ↓ Kafka
Kafka Hub (MSK)
    ↓ Kafka
Data/CS Agent (Server)
```

### 2.2 Topic 설계
- `agent.cards`: AgentCard 발행 (Compacted)
- `agent.{name}.requests`: 요청 topic
- `agent.{name}.responses`: 응답 topic

### 2.3 메시지 흐름
1. Balance Agent → Kafka (요청)
2. Data Agent ← Kafka (요청 수신)
3. Data Agent → Kafka (응답)
4. Balance Agent ← Kafka (응답 수신)

**핵심**: Correlation ID로 요청-응답 매칭

---

## 3. 핵심 구현 (15분)

### 3.1 KafkaTransport (Client-side) - 5분

**역할**: A2A Client가 Kafka를 통해 통신

**핵심 로직**:
1. Correlation ID 생성 (요청-응답 매칭)
2. Kafka Producer로 요청 발행
3. 백그라운드 Consumer로 응답 수신
4. Queue로 요청자에게 응답 전달

**데모 포인트**:
- 동시 요청도 정확히 매칭됨
- 스트리밍 지원 (실시간 thinking)

### 3.2 KafkaConsumerHandler (Server-side) - 5분

**역할**: Kafka 요청을 받아 처리

**핵심 로직**:
1. Kafka Consumer로 요청 수신
2. DefaultRequestHandler에게 위임 (재사용!)
3. 이벤트를 Kafka로 스트리밍
4. 응답 발행

**데모 포인트**:
- DefaultRequestHandler 재사용 (코드 중복 제거)
- HTTP/Kafka 동일한 비즈니스 로직

### 3.3 Agent Discovery (agent.cards) - 3분

**역할**: 동적 에이전트 발견

**핵심 로직**:
1. 각 에이전트가 시작 시 Card 발행
2. Balance Agent가 agent.cards 구독
3. Tool 동적 생성

**데모 포인트**:
- HTTP GET /card 불필요
- 에이전트 추가 시 자동 발견

### 3.4 주요 해결 과제 - 2분

1. **Correlation ID 매칭**: UUID + Dictionary
2. **스트리밍**: `final` 플래그 + 이벤트 타입
3. **DefaultRequestHandler 재사용**: Transport 분리
4. **백그라운드 Consumer**: asyncio.create_task()

---

## 4. 데모 (5분)

### 4.1 시스템 시작
```bash
# Kafka 시작
docker-compose up -d

# 에이전트 시작
./start_agents.sh

# GUI 시작
./start_gui.sh
```

### 4.2 실제 동작 확인
1. **Balance Agent GUI 접속**
2. **요청**: "테란과 저그의 밸런스를 분석해줘"
3. **확인 사항**:
   - Data Agent 호출 (게임 통계)
   - CS Agent 호출 (유저 피드백)
   - 실시간 thinking 표시
   - 종합 분석 결과

### 4.3 Kafka 메시지 확인
```bash
# agent.cards 확인
kafka-console-consumer --topic agent.cards

# 요청/응답 확인
kafka-console-consumer --topic agent.data.requests
kafka-console-consumer --topic agent.data.responses
```

---

## 5. HTTP vs Kafka 비교 (3분)

### 5.1 Discovery
| HTTP | Kafka |
|------|-------|
| URL 필요 | Agent 이름만 |
| HTTP GET /card | agent.cards 구독 |
| N번 요청 | 1번 구독 |

### 5.2 통신
| HTTP | Kafka |
|------|-------|
| HTTP POST | Kafka Produce |
| HTTP Response | Kafka Consume |
| 영속성 없음 | Kafka 로그 저장 |

### 5.3 확장성
| HTTP | Kafka |
|------|-------|
| N² 연결 | N+M 연결 |
| URL 관리 필요 | Topic 이름만 |
| 장애 전파 | 장애 격리 |

---

## 6. 결과 및 성과 (2분)

### 6.1 달성한 것
✅ A2A 프로토콜 완전 유지 (스트리밍, 멀티턴, Task 관리)
✅ Kafka Transport 구현 (HTTP 대체)
✅ 코드 변경 최소 (Transport만 교체)
✅ Hub-Spoke 아키텍처 (확장성 확보)
✅ 동적 Agent Discovery (agent.cards)

### 6.2 핵심 성과
- **확장성**: N² → N+M 연결
- **영속성**: 모든 메시지 Kafka에 저장
- **느슨한 결합**: URL 불필요, 장애 격리
- **재사용성**: DefaultRequestHandler 재사용

---

## 7. 향후 계획 (2분)

### 7.1 단기 (1-2주)
- MSK 배포 (Terraform)
- 모니터링 (Prometheus + Grafana)
- 성능 최적화

### 7.2 중기 (1-2개월)
- 에러 처리 강화 (Dead Letter Queue)
- 보안 (SSL, SASL)
- 멀티 리전 지원

### 7.3 장기 (3-6개월)
- 프로덕션 배포
- 다른 프로젝트 적용
- A2A + Kafka 패턴 표준화

---

## 8. Q&A (5분)

### 예상 질문

**Q1: HTTP보다 느리지 않나요?**
A: Kafka는 배치 처리와 압축으로 높은 처리량 제공. 레이턴시는 약간 증가하지만 (수 ms), 확장성과 영속성 장점이 더 큼.

**Q2: Kafka가 다운되면?**
A: MSK는 Multi-AZ로 고가용성 제공. Kafka 클러스터 자체가 SPOF가 되지 않도록 설계됨.

**Q3: 기존 A2A 에이전트와 호환되나요?**
A: Transport만 교체하면 됨. A2A 프로토콜은 그대로 유지되므로 호환성 100%.

**Q4: 멀티턴 대화는 어떻게?**
A: context_id로 대화 연결. TaskStore에 상태 저장. HTTP와 동일하게 작동.

**Q5: 성능은?**
A: 로컬 테스트에서 초당 수백 개 메시지 처리. MSK에서는 더 높은 처리량 가능.

---

## 발표 팁

### 시간 배분
- 문제 정의: 3분
- 아키텍처: 5분
- 핵심 구현: 15분 (가장 중요!)
- 데모: 5분
- 비교: 3분
- 결과: 2분
- 향후 계획: 2분
- Q&A: 5분

### 강조할 포인트
1. **DefaultRequestHandler 재사용** → 코드 중복 제거
2. **Correlation ID** → 비동기 매칭의 핵심
3. **agent.cards** → 동적 Discovery
4. **Hub-Spoke** → 확장성의 핵심

### 데모 시나리오
1. 시스템 시작 (미리 준비)
2. GUI에서 요청
3. 실시간 thinking 표시
4. Kafka 메시지 확인 (터미널)
5. 최종 결과 확인

### 슬라이드 구성 (선택사항)
1. 제목 슬라이드
2. 문제 정의 (HTTP 한계)
3. 아키텍처 다이어그램
4. KafkaTransport 로직
5. KafkaConsumerHandler 로직
6. Agent Discovery (agent.cards)
7. 데모 화면
8. HTTP vs Kafka 비교표
9. 결과 및 성과
10. Q&A

---

## 백업 자료

### 상세 코드 (질문 대비)
- `kafka/kafka_transport.py`
- `kafka/kafka_consumer_handler.py`
- `kafka/agent_registry.py`

### 문서
- `IMPLEMENTATION_SUMMARY.md`
- `LOGIC_COMPARISON.md`
- `TASK_MANAGEMENT.md`

### 데모 환경
- 로컬 Kafka (docker-compose)
- 3개 에이전트 (Balance, Data, CS)
- 3개 GUI (Streamlit)
