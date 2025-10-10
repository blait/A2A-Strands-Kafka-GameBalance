import pandas as pd
import logging
import uuid
from typing import Literal
from pydantic import BaseModel
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatus, Artifact, TaskStatusUpdateEvent, TaskArtifactUpdateEvent, TextPart
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

logger = logging.getLogger(__name__)

GAME_DATA = [
    {"game_id": 1, "race": "Terran", "result": "win", "duration": 15},
    {"game_id": 2, "race": "Zerg", "result": "loss", "duration": 20},
    {"game_id": 3, "race": "Protoss", "result": "win", "duration": 18},
    {"game_id": 4, "race": "Terran", "result": "win", "duration": 12},
    {"game_id": 5, "race": "Zerg", "result": "win", "duration": 25},
    {"game_id": 6, "race": "Protoss", "result": "loss", "duration": 19},
]

@tool
def analyze_win_rates(race: str) -> str:
    """종족별 승률 분석"""
    df = pd.DataFrame(GAME_DATA)
    race_data = df[df['race'] == race]
    if len(race_data) == 0:
        return f"{race} 데이터 없음"
    wins = len(race_data[race_data['result'] == 'win'])
    total = len(race_data)
    win_rate = (wins / total) * 100
    return f"{race} 승률: {win_rate:.1f}% ({wins}/{total})"

@tool
def analyze_game_duration(race: str) -> str:
    """종족별 평균 게임 시간"""
    df = pd.DataFrame(GAME_DATA)
    race_data = df[df['race'] == race]
    if len(race_data) == 0:
        return f"{race} 데이터 없음"
    avg_duration = race_data['duration'].mean()
    return f"{race} 평균 게임 시간: {avg_duration:.1f}분"

agent = Agent(
    name="Data Analysis Agent",
    model=BedrockModel(model_id="us.amazon.nova-lite-v1:0", temperature=0.3),
    tools=[analyze_win_rates, analyze_game_duration],
    system_prompt="""당신은 데이터 분석가입니다.

도구:
- analyze_win_rates: 종족별 승률 분석
- analyze_game_duration: 평균 게임 시간 분석

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
- status='input_required': 사용자가 종족(테란/저그/프로토스)을 명시하지 않았을 때
- status='completed': 분석을 완료했을 때
- status='error': 에러 발생 시

**중요: 사용자가 "승률"이라고만 물어보면 어떤 종족인지 반드시 되물으세요.**

모든 응답은 한글로 작성하세요."""
)

class DataAnalysisExecutor(AgentExecutor):
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
            
            logger.info(f"Executing task {context.task_id}: '{input_text}'")
            
            # 대화 히스토리 구성
            conversation_history = []
            if context.current_task and hasattr(context.current_task, 'artifacts'):
                # 이전 artifacts에서 대화 히스토리 추출
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
            
            logger.info(f"Full context: {full_input}")
            
            # Agent 스트리밍 실행
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
            
            logger.info(f"Agent response: {full_response}")
            response = full_response
            
            # JSON 파싱 시도
            try:
                import json
                import re
                # <thinking> 및 <response> 태그 제거
                clean_response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'<response>|</response>', '', clean_response, flags=re.DOTALL).strip()
                response_data = json.loads(clean_response)
                status = response_data.get('status', 'completed')
                message = response_data.get('message', response)
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
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                artifact=artifact
            ))
            
            # 상태에 따라 Task 업데이트
            if status == 'input_required':
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    status=TaskStatus(state=TaskState.input_required),
                    final=True
                ))
            elif status == 'error':
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    status=TaskStatus(state=TaskState.failed),
                    final=True
                ))
            else:  # completed
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    status=TaskStatus(state=TaskState.completed),
                    final=True
                ))
                
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
