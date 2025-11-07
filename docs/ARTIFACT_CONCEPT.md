# Artifact 개념 정리

## 정답: Artifact는 모든 응답에 만들어집니다! ✅

**Artifact = Agent의 모든 출력 (중간 질문, 최종 결과 모두 포함)**

---

## Artifact란?

### A2A 프로토콜의 정의

**Artifact는 Agent가 생성한 모든 출력물입니다.**

```python
# a2a/types.py
class Artifact:
    """Agent가 생성한 출력물"""
    
    artifact_id: str
    parts: List[Part]  # 텍스트, 이미지, 파일 등
    metadata: Optional[Dict] = None
```

**핵심:**
- 최종 결과만이 아님
- 중간 질문도 Artifact
- Agent의 모든 응답이 Artifact

---

## Artifact의 종류

### 1. 중간 질문 (input_required)

```python
# Status: input_required
artifact = Artifact(
    artifact_id="artifact-1",
    parts=[TextPart(text="어떤 종족의 승률을 알려드릴까요?")]
)
```

**이것도 Artifact입니다!**
- Agent가 생성한 출력
- 사용자에게 보여줄 내용
- Task의 artifacts에 추가됨

### 2. 중간 결과 (working)

```python
# Status: working
artifact = Artifact(
    artifact_id="artifact-2",
    parts=[TextPart(text="데이터를 분석 중입니다...")]
)
```

**이것도 Artifact입니다!**
- 진행 상황 표시
- 실시간 피드백

### 3. 최종 결과 (completed)

```python
# Status: completed
artifact = Artifact(
    artifact_id="artifact-3",
    parts=[TextPart(text="테란 승률: 58%")]
)
```

**이것도 Artifact입니다!**
- 최종 결과물
- 작업 완료

### 4. 에러 메시지 (failed)

```python
# Status: failed
artifact = Artifact(
    artifact_id="artifact-4",
    parts=[TextPart(text="데이터를 찾을 수 없습니다.")]
)
```

**이것도 Artifact입니다!**
- 에러 정보
- 사용자에게 표시

---

## Task와 Artifact의 관계

### Task 구조

```python
class Task:
    task_id: str
    status: TaskStatus  # working, input_required, completed, failed
    artifacts: List[Artifact]  # 여러 개 가능!
    message: Message
```

**핵심:**
- Task는 여러 개의 Artifact를 가질 수 있음
- Status와 관계없이 Artifact 생성 가능

---

## 실제 예시

### 시나리오: "승률 알려줘" → "테란"

#### 1번째 요청: "승률 알려줘"

```python
# AgentExecutor
async def execute(self, context, event_queue):
    # 추가 정보 필요 판단
    
    # Artifact 생성 (중간 질문)
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        taskId=context.task_id,
        artifact=Artifact(
            artifact_id="artifact-1",
            parts=[TextPart(text="어떤 종족의 승률을 알려드릴까요?")]
        )
    ))
    
    # Status 업데이트
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        taskId=context.task_id,
        status=TaskStatus(state="input_required"),
        final=True
    ))
```

**결과 Task:**
```python
Task(
    task_id="task-1",
    status="input_required",
    artifacts=[
        Artifact(
            artifact_id="artifact-1",
            parts=[TextPart(text="어떤 종족의 승률을 알려드릴까요?")]
        )
    ]
)
```

**GUI 표시:**
```
Assistant: 어떤 종족의 승률을 알려드릴까요?
[입력 대기 중...]
```

#### 2번째 요청: "테란"

```python
# AgentExecutor
async def execute(self, context, event_queue):
    # 데이터 분석
    result = "테란 승률: 58%"
    
    # Artifact 생성 (최종 결과)
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        taskId=context.task_id,
        artifact=Artifact(
            artifact_id="artifact-2",
            parts=[TextPart(text=result)]
        )
    ))
    
    # Status 업데이트
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        taskId=context.task_id,
        status=TaskStatus(state="completed"),
        final=True
    ))
```

**결과 Task:**
```python
Task(
    task_id="task-2",
    status="completed",
    artifacts=[
        Artifact(
            artifact_id="artifact-2",
            parts=[TextPart(text="테란 승률: 58%")]
        )
    ]
)
```

**GUI 표시:**
```
Assistant: 테란 승률: 58%
[완료]
```

---

## 여러 개의 Artifact

### 진행 상황 표시

```python
# AgentExecutor
async def execute(self, context, event_queue):
    # 1. 시작 메시지
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        artifact=Artifact(
            artifact_id="artifact-1",
            parts=[TextPart(text="데이터를 로드하는 중...")]
        )
    ))
    
    # 2. 진행 중
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        artifact=Artifact(
            artifact_id="artifact-2",
            parts=[TextPart(text="분석을 수행하는 중...")]
        )
    ))
    
    # 3. 최종 결과
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        artifact=Artifact(
            artifact_id="artifact-3",
            parts=[TextPart(text="테란 승률: 58%")]
        )
    ))
    
    # Status 업데이트
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        status=TaskStatus(state="completed"),
        final=True
    ))
```

**결과 Task:**
```python
Task(
    task_id="task-1",
    status="completed",
    artifacts=[
        Artifact(parts=[TextPart(text="데이터를 로드하는 중...")]),
        Artifact(parts=[TextPart(text="분석을 수행하는 중...")]),
        Artifact(parts=[TextPart(text="테란 승률: 58%")])
    ]
)
```

**GUI 표시:**
```
Assistant: 
  데이터를 로드하는 중...
  분석을 수행하는 중...
  테란 승률: 58%
[완료]
```

---

## Status vs Artifact

### Status (작업 상태)

```python
class TaskStatus:
    state: str  # working, input_required, completed, failed
```

**의미:**
- 작업의 현재 상태
- 다음 액션 결정
- GUI 표시 제어

### Artifact (출력물)

```python
class Artifact:
    parts: List[Part]  # 실제 내용
```

**의미:**
- Agent가 생성한 내용
- 사용자에게 보여줄 것
- 작업의 결과물

### 관계

```
Status: input_required
  → Artifact: "어떤 종족?"
  → GUI: 질문 표시 + 입력 대기

Status: working
  → Artifact: "분석 중..."
  → GUI: 진행 상황 표시

Status: completed
  → Artifact: "테란 승률 58%"
  → GUI: 결과 표시 + 완료
```

---

## 코드로 확인

### AgentExecutor에서 Artifact 생성

```python
# agents/data_analysis_agent_executor.py
class DataAnalysisExecutor(AgentExecutor):
    async def execute(self, context, event_queue):
        input_text = context.message.parts[0].text
        
        # 입력 검증
        if "승률" in input_text and "종족" not in input_text:
            # 추가 정보 필요
            
            # Artifact 생성 (질문)
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                taskId=context.task_id,
                artifact=Artifact(
                    artifact_id=f"artifact-{context.task_id}",
                    parts=[TextPart(text="어떤 종족의 승률을 알려드릴까요?")]
                )
            ))
            
            # Status: input_required
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                taskId=context.task_id,
                status=TaskStatus(state="input_required"),
                final=True
            ))
        else:
            # 정보 충분
            
            # 데이터 분석
            result = self.analyze_data(input_text)
            
            # Artifact 생성 (결과)
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                taskId=context.task_id,
                artifact=Artifact(
                    artifact_id=f"artifact-{context.task_id}",
                    parts=[TextPart(text=result)]
                )
            ))
            
            # Status: completed
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                taskId=context.task_id,
                status=TaskStatus(state="completed"),
                final=True
            ))
```

### GUI에서 Artifact 표시

```python
# gui/balance_gui.py
async def handle_response(self, event):
    if isinstance(event, TaskArtifactUpdateEvent):
        # Artifact 내용 추출
        text = event.artifact.parts[0].text
        
        # 화면에 표시
        st.write(text)
    
    elif isinstance(event, TaskStatusUpdateEvent):
        # Status에 따라 UI 변경
        if event.status.state == "input_required":
            st.info("추가 정보가 필요합니다")
            # 입력창 활성화
        elif event.status.state == "completed":
            st.success("완료")
        elif event.status.state == "failed":
            st.error("실패")
```

---

## Artifact의 다양한 타입

### 텍스트

```python
Artifact(
    parts=[TextPart(text="테란 승률 58%")]
)
```

### 이미지

```python
Artifact(
    parts=[ImagePart(url="https://example.com/chart.png")]
)
```

### 파일

```python
Artifact(
    parts=[FilePart(
        name="report.pdf",
        url="https://example.com/report.pdf"
    )]
)
```

### 여러 Part

```python
Artifact(
    parts=[
        TextPart(text="분석 결과:"),
        ImagePart(url="https://example.com/chart.png"),
        TextPart(text="테란 승률 58%")
    ]
)
```

---

## 정리

### Artifact의 정의

**Artifact = Agent가 생성한 모든 출력물**

- ✅ 중간 질문 (input_required)
- ✅ 진행 상황 (working)
- ✅ 최종 결과 (completed)
- ✅ 에러 메시지 (failed)

### Status vs Artifact

| Status | Artifact | 의미 |
|--------|----------|------|
| `input_required` | "어떤 종족?" | 추가 정보 필요 |
| `working` | "분석 중..." | 작업 진행 중 |
| `completed` | "테란 승률 58%" | 작업 완료 |
| `failed` | "에러 발생" | 작업 실패 |

### 핵심

```
Task {
    status: "input_required"  ← 상태
    artifacts: [
        Artifact {
            parts: ["어떤 종족?"]  ← 출력물
        }
    ]
}
```

**Status는 상태, Artifact는 내용!**

### 오해 바로잡기

❌ **잘못된 이해**: Artifact는 최종 결과만
✅ **올바른 이해**: Artifact는 모든 출력 (질문, 진행, 결과, 에러)

❌ **잘못된 이해**: input_required는 Artifact 없음
✅ **올바른 이해**: input_required도 Artifact 있음 (질문 내용)

❌ **잘못된 이해**: Task당 Artifact 1개
✅ **올바른 이해**: Task당 Artifact 여러 개 가능

**Artifact = Agent의 모든 말 (질문, 답변, 진행 상황 모두)** 💬
