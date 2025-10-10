# 🚀 빠른 시작 가이드

## 현재 실행 중인 시스템

### ✅ 에이전트 (Kafka 기반)
- **Balance Agent** (포트 9001) - 코디네이터
- **CS Agent** (포트 9002) - 피드백 조회
- **Data Agent** (포트 9003) - 통계 분석

### ✅ GUI (Streamlit)
- **Balance GUI**: http://localhost:8501
- **CS GUI**: http://localhost:8502
- **Data GUI**: http://localhost:8503

## 테스트 시나리오

### 1. Balance Agent (8501) - 종합 분석
```
"저그 승률과 피드백 모두 알려줘"
```
→ Data Agent와 CS Agent를 동시에 호출하여 종합 정보 제공

```
"테란 관련 모든 정보 보여줘"
```
→ 테란 승률 + 테란 피드백 통합 분석

### 2. CS Agent (8502) - 피드백 조회
```
"테란 피드백 보여줘"
```
→ 테란 관련 피드백만 필터링

```
"긴급도 높은 피드백"
```
→ 우선순위 높은 피드백 조회

### 3. Data Agent (8503) - 통계 분석
```
"테란 승률은?"
```
→ 테란 승률 분석

```
"전체 게임 통계"
```
→ 모든 종족 통계 제공

## 특징

### 🔄 실시간 스트리밍
- 에이전트의 사고 과정을 실시간으로 확인
- "🧠 사고 과정 보기" 클릭하여 상세 로그 확인

### 💬 Multi-turn 대화
- 이전 대화 맥락 유지
- 추가 질문 가능 (예: "더 자세히", "다른 종족은?")

### 🔗 Kafka 통신
- Balance Agent → Data/CS Agent 호출 시 Kafka 사용
- 비동기 메시징으로 안정적 통신

## 시스템 관리

### 에이전트 재시작
```bash
./start_agents.sh
```

### GUI 재시작
```bash
pkill -f streamlit
./venv/bin/streamlit run gui/balance_gui.py --server.port 8501 &
./venv/bin/streamlit run gui/cs_gui.py --server.port 8502 &
./venv/bin/streamlit run gui/analysis_gui.py --server.port 8503 &
```

### 전체 종료
```bash
pkill -f "python.*agent.py"
pkill -f streamlit
```

## 로그 확인

```bash
# 에이전트 로그
tail -f data_agent.log
tail -f cs_agent.log
tail -f balance_agent.log

# GUI 로그
tail -f /tmp/gui_balance.log
tail -f /tmp/gui_cs.log
```

## 아키텍처

```
Browser (8501/8502/8503)
    ↓ HTTP
Agent HTTP Server (9001/9002/9003)
    ↓ Kafka
Kafka Hub (localhost:9092)
    ↓
Agent Executors (Strands)
```

## 현재 상태: ✅ 모두 실행 중!

이제 브라우저에서 http://localhost:8501 로 접속하여 테스트하세요!
