# Kafka Transport vs HTTP Transport 비교

## 현재 아키텍처 (HTTP)

```
Balance Agent
    ↓ HTTP POST http://localhost:9003
Data Agent (port 9003)

    ↓ HTTP POST http://localhost:9002
CS Agent (port 9002)
```

### 문제점

❌ **포트 관리 필요**
- Data Agent: 9003
- CS Agent: 9002
- Balance Agent: 9001
- 에이전트 추가 시마다 포트 할당 필요

❌ **URL 하드코딩**
```python
self.agents = {
    "data": "http://localhost:9003",
    "cs": "http://localhost:9002"
}
```

❌ **N² 연결 복잡도**
```
3개 에이전트 = 6개 연결
10개 에이전트 = 90개 연결
```

❌ **장애 전파**
```
Data Agent 다운
    ↓
Balance Agent 타임아웃 (30초 대기)
    ↓
전체 시스템 느려짐
```

❌ **메시지 손실**
```
Data Agent 재시작 중
    ↓
Balance Agent 요청 → 실패
    ↓
재시도 로직 없으면 손실
```

❌ **확장 어려움**
```
Data Agent 부하 증가
    ↓
인스턴스 추가 → 로드밸런서 필요
    ↓
복잡도 증가
```

---

## Kafka Transport 아키텍처

```
Balance Agent
    ↓ Kafka Produce
Kafka Hub (localhost:9092)
    ↓ Kafka Consume
Data Agent (포트 불필요)
CS Agent (포트 불필요)
```

### 개선점

## 1. 포트 관리 불필요 ✅

**Before:**
```python
# 각 에이전트마다 포트 필요
uvicorn.run(app, host="0.0.0.0", port=9003)  # Data
uvicorn.run(app, host="0.0.0.0", port=9002)  # CS
uvicorn.run(app, host="0.0.0.0", port=9001)  # Balance
```

**After:**
```python
# 포트 불필요, Kafka만 연결
consumer = KafkaConsumerHandler("data", executor)
await consumer.start()
```

**효과:**
- 포트 충돌 걱정 없음
- 방화벽 설정 간단 (9092만 열면 됨)
- Docker/K8s 배포 시 포트 매핑 불필요

---

## 2. URL 관리 불필요 ✅

**Before:**
```python
# URL 변경 시 코드 수정 필요
self.agents = {
    "data": "http://localhost:9003",  # 로컬
    "data": "http://data-agent.prod:9003",  # 프로덕션
}
```

**After:**
```python
# 에이전트 이름만 알면 됨
transport = KafkaTransport(target_agent_name="data")
```

**효과:**
- 환경별 설정 불필요
- Service Discovery 자동
- 에이전트 이동/재배포 시 코드 변경 없음

---

## 3. 선형 연결 복잡도 ✅

**Before (N²):**
```
3개 에이전트 → 6개 HTTP 연결
10개 에이전트 → 90개 HTTP 연결
```

**After (N+M):**
```
3개 에이전트 → 3개 Kafka 연결
10개 에이전트 → 10개 Kafka 연결
```

**효과:**
- 에이전트 추가 시 복잡도 선형 증가
- 네트워크 연결 수 감소
- 관리 포인트 단순화

---

## 4. 장애 격리 ✅

**Before:**
```
Data Agent 다운
    ↓
Balance Agent 요청 → 30초 타임아웃
    ↓
사용자 대기
```

**After:**
```
Data Agent 다운
    ↓
Balance Agent 요청 → Kafka에 저장
    ↓
Data Agent 복구 → 자동 처리
    ↓
사용자는 모름
```

**효과:**
- 일시적 장애 영향 최소화
- 자동 재시도
- 메시지 손실 방지

---

## 5. 메시지 영속성 ✅

**Before:**
```
Balance → Data 요청
    ↓
Data Agent 처리 중 크래시
    ↓
메시지 손실
```

**After:**
```
Balance → Kafka (디스크 저장)
    ↓
Data Agent 크래시
    ↓
Data Agent 재시작 → Kafka에서 재처리
```

**효과:**
- 메시지 손실 방지
- 감사 로그 자동 생성
- 디버깅 용이 (메시지 재생 가능)

---

## 6. 자동 부하 분산 ✅

**Before:**
```
Data Agent 부하 증가
    ↓
수동으로 로드밸런서 설정
    ↓
복잡한 인프라
```

**After:**
```
Data Agent #1 (Consumer Group: data)
Data Agent #2 (Consumer Group: data)
Data Agent #3 (Consumer Group: data)
    ↓
Kafka가 자동 분산
```

**효과:**
- 인스턴스 추가만 하면 자동 분산
- 로드밸런서 불필요
- 수평 확장 간단

---

## 7. 비동기 처리 가능 ✅

**Before:**
```python
# 동기 대기만 가능
response = await call_agent("data", query)  # 30초 대기
```

**After:**
```python
# 비동기 처리 선택 가능
await kafka.publish(query)  # 즉시 리턴
# 나중에 응답 받음 (webhook, polling 등)
```

**효과:**
- 긴 작업도 타임아웃 없음
- 사용자 경험 개선
- 백그라운드 작업 가능

---

## 8. Fan-Out 패턴 ✅

**Before:**
```python
# 여러 에이전트 호출 시 순차 처리
result1 = await call_agent("data", query)
result2 = await call_agent("cs", query)
result3 = await call_agent("analytics", query)
# 총 시간 = 합산
```

**After:**
```python
# 한 번 발행 → 여러 에이전트 동시 처리
await kafka.publish("agent.broadcast", query)
# Data, CS, Analytics 동시 처리
# 총 시간 = 가장 느린 것
```

**효과:**
- 병렬 처리
- 응답 시간 단축
- 새 에이전트 추가 시 코드 변경 없음

---

## 9. 모니터링 & 디버깅 ✅

**Before:**
```
# HTTP 로그 분산
Balance Agent 로그
Data Agent 로그
CS Agent 로그
→ 추적 어려움
```

**After:**
```
# Kafka에 모든 메시지 기록
Kafka Topic: agent.data.requests
Kafka Topic: agent.data.responses
→ 중앙 집중식 로그
→ 메시지 재생 가능
```

**효과:**
- 전체 흐름 추적 용이
- 디버깅 시간 단축
- 성능 분석 가능

---

## 10. AWS 통합 ✅

**Before:**
```
HTTP → ALB → ECS/EKS
- ALB 비용
- Health Check 설정
- Target Group 관리
```

**After:**
```
Kafka → MSK → ECS/EKS
- MSK 관리형 서비스
- Auto Scaling 내장
- 고가용성 기본 제공
```

**효과:**
- 인프라 관리 간소화
- AWS 네이티브 통합
- 비용 최적화

---

## 실제 시나리오 비교

### 시나리오: "테란 승률 분석 요청"

#### HTTP 방식
```
1. Balance Agent → Data Agent HTTP 요청 (0.1초)
2. Data Agent 처리 (2초)
3. Data Agent → Balance Agent HTTP 응답 (0.1초)
4. Balance Agent → CS Agent HTTP 요청 (0.1초)
5. CS Agent 처리 (1초)
6. CS Agent → Balance Agent HTTP 응답 (0.1초)

총 시간: 3.4초
문제: Data Agent 다운 시 전체 실패
```

#### Kafka 방식
```
1. Balance Agent → Kafka (0.01초)
2. Data Agent & CS Agent 동시 처리 (2초)
3. Kafka → Balance Agent (0.01초)

총 시간: 2.02초 (40% 단축)
장점: Data Agent 다운 시 메시지 보존, 복구 후 자동 처리
```

---

## 단점 (트레이드오프)

### Kafka 방식의 단점

❌ **인프라 복잡도**
- Kafka 클러스터 운영 필요
- Zookeeper 관리 (Kafka 3.x 이전)

❌ **학습 곡선**
- Kafka 개념 이해 필요
- Topic, Partition, Consumer Group 등

❌ **초기 설정**
- Topic 생성
- Retention 정책 설정
- 모니터링 구성

❌ **로컬 개발**
- Docker Compose 필요
- 메모리 사용량 증가 (Kafka 실행)

### 언제 HTTP가 나을까?

✅ **간단한 프로토타입**
- 에이전트 2-3개
- 트래픽 적음
- 빠른 개발 필요

✅ **동기 요청-응답만 필요**
- 비동기 불필요
- 메시지 영속성 불필요

✅ **인프라 제약**
- Kafka 운영 불가
- 클라우드 비용 제약

---

## 결론

### Kafka Transport를 선택해야 하는 경우

✅ 에이전트 5개 이상
✅ 높은 가용성 필요
✅ 메시지 손실 방지 필요
✅ 확장성 중요
✅ AWS MSK 사용 가능
✅ 비동기 처리 필요
✅ 감사 로그 필요

### HTTP Transport를 유지해야 하는 경우

✅ 프로토타입/POC
✅ 에이전트 2-3개
✅ 간단한 동기 통신만 필요
✅ 인프라 최소화
✅ 빠른 개발 우선

---

## 이 프로젝트에서는?

**현재 상황:**
- 에이전트 3개 (Balance, Data, CS)
- 데모/학습 목적
- AWS MSK 활용 목표

**추천:**
✅ **Kafka Transport 적용**

**이유:**
1. MSK 데모가 목적
2. Hub-Spoke 아키텍처 학습
3. 확장 가능한 구조 경험
4. AWS 통합 실습

**단, HTTP도 유지:**
- 개발 시 HTTP로 빠른 테스트
- 프로덕션은 Kafka 사용
- 두 방식 비교 가능
