import logging
import uuid
import json
import re
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatus, Artifact, TaskStatusUpdateEvent, TaskArtifactUpdateEvent, TextPart
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

logger = logging.getLogger(__name__)

FEEDBACK_DATA = [
    {"race": "Terran", "complaint": "테란 마린 러시가 너무 강력합니다. 초반 방어가 불가능해요.", "upvotes": 245, "urgency": "high", "date": "2025-10-01"},
    {"race": "Zerg", "complaint": "저그 뮤탈이 너프되어서 이제 쓸모가 없습니다.", "upvotes": 312, "urgency": "high", "date": "2025-10-01"},
    {"race": "Protoss", "complaint": "프로토스 광전사 체력이 너무 약합니다.", "upvotes": 189, "urgency": "medium", "date": "2025-10-02"},
    {"race": "Terran", "complaint": "테란 벙커 건설 속도가 너무 빨라서 러시 방어가 쉽습니다.", "upvotes": 201, "urgency": "high", "date": "2025-10-03"},
    {"race": "Zerg", "complaint": "저그 히드라 사거리가 짧아서 쓸모가 없어요.", "upvotes": 156, "urgency": "medium", "date": "2025-10-03"},
    {"race": "Protoss", "complaint": "프로토스 스톰 데미지가 너무 강력합니다.", "upvotes": 267, "urgency": "high", "date": "2025-10-04"},
]

@tool
def get_feedback(urgency: str = None, race: str = None) -> str:
    """Get customer feedback from game forums
    
    Args:
        urgency: Filter by urgency level (high, medium, low)
        race: Filter by race (Terran, Zerg, Protoss)
    """
    filtered = FEEDBACK_DATA
    if urgency:
        filtered = [f for f in filtered if f["urgency"] == urgency]
    if race:
        filtered = [f for f in filtered if f["race"] == race]
    
    result = []
    for f in filtered:
        result.append(f"[{f['race']}] {f['complaint']} (추천: {f['upvotes']}, 날짜: {f['date']})")
    
    return "\n".join(result) if result else "No feedback found"

agent = Agent(
    name="CS Feedback Agent",
    description="게임 포럼에서 고객 피드백을 조회하는 에이전트",
    model=BedrockModel(model_id="us.amazon.nova-lite-v1:0", temperature=0.3),
    tools=[get_feedback],
    system_prompt="""당신은 고객 지원 담당자입니다.

도구:
- get_feedback(race="Terran"): 특정 종족 피드백
- get_feedback(urgency="high"): 긴급도별 피드백

**중요: 도구 호출 시 종족명은 반드시 영어로 사용하세요:**
- 테란 → Terran
- 저그 → Zerg
- 프로토스 → Protoss

**응답 형식:**
반드시 JSON 형식으로 응답하세요:
{
  "status": "input_required" | "completed" | "error",
  "message": "사용자에게 보낼 메시지"
}

**상태 규칙:**
- status='input_required': 사용자가 종족(테란/저그/프로토스) 또는 긴급도를 명시하지 않았을 때
- status='completed': 피드백 조회를 완료했을 때
- status='error': 에러 발생 시

**중요: 사용자가 "피드백"이라고만 물어보면 어떤 종족 또는 긴급도인지 반드시 되물으세요.**

모든 응답은 한글로 작성하세요."""
)

class CSFeedbackExecutor(AgentExecutor):
    async def cancel(self, task_id: str) -> None:
        logger.info(f"Cancelling task {task_id}")
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            # Message에서 텍스트 추출
            input_text = ""
            if context.message and hasattr(context.message, 'parts') and context.message.parts:
                for part in context.message.parts:
                    if hasattr(part, 'root') and hasattr(part.root, 'text'):
                        input_text += part.root.text
            
            print(f"🔧 [CS Executor] Task {context.task_id}: '{input_text}'", flush=True)
            logger.info(f"Executing task {context.task_id}: '{input_text}'")
            
            # 대화 히스토리 구성
            conversation_history = []
            if context.current_task and hasattr(context.current_task, 'artifacts'):
                for artifact in context.current_task.artifacts:
                    if hasattr(artifact, 'parts'):
                        for part in artifact.parts:
                            if hasattr(part, 'text'):
                                conversation_history.append(part.text)
            
            # 전체 컨텍스트 구성
            if conversation_history:
                full_input = f"이전 대화:\n" + "\n".join(conversation_history) + f"\n\n현재 질문: {input_text}"
            else:
                full_input = input_text
            
            print(f"🔧 [CS Executor] Full context: {full_input[:100]}", flush=True)
            logger.info(f"Full context: {full_input}")
            
            # Agent 스트리밍 실행
            print(f"🔧 [CS Executor] Calling agent.stream_async...", flush=True)
            full_response = ""
            thinking_buffer = ""
            
            async for event in agent.stream_async(full_input):
                if isinstance(event, dict):
                    event_type = event.get('type')
                    
                    # Thinking 이벤트 - 실시간 전송
                    if event_type == 'thinking':
                        thinking_text = event.get('content', '')
                        thinking_buffer += thinking_text
                        # Thinking artifact 전송
                        await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                            taskId=context.task_id,
                            contextId=context.context_id,
                            artifact=Artifact(
                                artifactId=str(uuid.uuid4()),
                                parts=[TextPart(text=f"🧠 {thinking_buffer}")]
                            )
                        ))
                    
                    # 텍스트 델타
                    elif event_type == 'text_delta':
                        full_response += event.get('content', '')
                    
                    # 최종 메시지
                    elif event_type == 'message':
                        full_response = event.get('content', '')
            
            # 최종 응답 확인
            if not full_response:
                result = await agent.invoke_async(full_input)
                full_response = result.output if hasattr(result, 'output') else str(result)
            
            print(f"🔧 [CS Executor] Agent response: {full_response[:200]}", flush=True)
            logger.info(f"Agent response: {full_response}")
            response = full_response
            
            # JSON 파싱 시도
            try:
                # <thinking> 및 <response> 태그 제거
                clean_response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'<response>|</response>', '', clean_response, flags=re.DOTALL).strip()
                response_data = json.loads(clean_response)
                status = response_data.get('status', 'completed')
                message = response_data.get('message', response)
                print(f"🔧 [CS Executor] Parsed - status: {status}, message: {message[:100]}", flush=True)
                logger.info(f"Parsed status: {status}, message: {message[:100]}")
            except Exception as parse_error:
                # JSON 파싱 실패 시 기본값
                logger.warning(f"JSON parsing failed: {parse_error}, using defaults")
                status = 'completed'
                message = response
            
            # Artifact 생성 - 전체 JSON 응답 포함
            full_json = json.dumps({"status": status, "message": message}, ensure_ascii=False)
            artifact = Artifact(
                artifactId=str(uuid.uuid4()),
                parts=[TextPart(text=full_json)]
            )
            
            # Artifact 먼저 전송
            print(f"🔧 [CS Executor] Sending artifact...", flush=True)
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                artifact=artifact
            ))
            print(f"🔧 [CS Executor] Artifact sent", flush=True)
            
            # 상태에 따라 Task 업데이트
            if status == 'input_required':
                print(f"🔧 [CS Executor] Sending status: input_required", flush=True)
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    status=TaskStatus(state=TaskState.input_required),
                    final=True
                ))
            elif status == 'error':
                print(f"🔧 [CS Executor] Sending status: failed", flush=True)
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    status=TaskStatus(state=TaskState.failed),
                    final=True
                ))
            else:  # completed
                print(f"🔧 [CS Executor] Sending status: completed", flush=True)
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    status=TaskStatus(state=TaskState.completed),
                    final=True
                ))
            print(f"✅ [CS Executor] Task {context.task_id} completed", flush=True)
                
        except Exception as e:
            logger.error(f"Error executing task: {e}", exc_info=True)
            error_artifact = Artifact(
                artifactId=str(uuid.uuid4()),
                parts=[TextPart(text=f"에러 발생: {str(e)}")]
            )
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                artifact=error_artifact
            ))
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                status=TaskStatus(state=TaskState.failed),
                final=True
            ))
