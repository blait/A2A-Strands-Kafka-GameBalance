import logging
import json
import re
from uuid import uuid4
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatus, Artifact, TaskStatusUpdateEvent, TaskArtifactUpdateEvent, TextPart, Message, Part, Role, MessageSendParams
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from kafka.kafka_transport import KafkaTransport
from kafka.agent_registry import discover_agents

logger = logging.getLogger(__name__)

# A2A client
class A2AClient:
    def __init__(self, bootstrap_servers="localhost:9092"):
        self.bootstrap_servers = bootstrap_servers
        self.agent_cards = {}
        self.transports = {}
        self._initialized = False
    
    async def init(self):
        if self._initialized:
            return
        self.agent_cards = await discover_agents(self.bootstrap_servers)
        self._initialized = True
    
    def get_transport(self, agent_id: str):
        if agent_id not in self.transports:
            self.transports[agent_id] = KafkaTransport(
                target_agent_name=agent_id,
                bootstrap_servers=self.bootstrap_servers
            )
        return self.transports[agent_id]

a2a_client = A2AClient()

def create_agent_tool(agent_id: str, agent_name: str, description: str):
    @tool
    async def call_agent(query: str) -> str:
        f"""Call {agent_name}: {description}"""
        transport = a2a_client.get_transport(agent_id)
        
        msg = Message(
            kind="message",
            role=Role.user,
            parts=[Part(TextPart(kind="text", text=query))],
            message_id=uuid4().hex
        )
        
        result = await transport.send_message(MessageSendParams(message=msg))
        
        response_text = ""
        if hasattr(result, 'artifacts') and result.artifacts:
            for artifact in result.artifacts:
                if hasattr(artifact, 'parts'):
                    for part in artifact.parts:
                        if hasattr(part, 'root') and hasattr(part.root, 'text'):
                            response_text += part.root.text
        
        return response_text if response_text else "No response"
    
    call_agent.__name__ = f"call_{agent_id}_agent"
    return call_agent

# Agent creation
async def create_agent():
    await a2a_client.init()
    
    tools = []
    for agent_id, card in a2a_client.agent_cards.items():
        if agent_id == "balance":
            continue
        skills_desc = ", ".join([s.get('description', '') for s in card.get('skills', [])])
        tool_func = create_agent_tool(agent_id, card['name'], skills_desc)
        tools.append(tool_func)
    
    return Agent(
        name="Game Balance Agent",
        model=BedrockModel(model_id="us.amazon.nova-lite-v1:0", temperature=0.3),
        tools=tools,
        system_prompt="""당신은 게임 밸런스 조정 담당자입니다.

**필수: 사용자가 게임 데이터를 물어보면 반드시 사용 가능한 도구를 사용하세요.**

**응답 형식 (JSON):**
{
  "status": "completed" | "input-required" | "failed",
  "message": "사용자에게 보여줄 메시지"
}

**중요: 모든 응답은 한글로 작성하세요.**"""
    )

agent = None

class GameBalanceExecutor(AgentExecutor):
    async def cancel(self, task_id: str) -> None:
        logger.info(f"Cancelling task {task_id}")
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        global agent
        
        print(f"🔧 [Executor] Starting execution for task {context.task_id}", flush=True)
        
        # Create agent if not exists
        if agent is None:
            print(f"🔧 [Executor] Creating agent...", flush=True)
            agent = await create_agent()
            print(f"🔧 [Executor] Agent created", flush=True)
        
        try:
            # Extract input text
            input_text = ""
            if context.message and hasattr(context.message, 'parts') and context.message.parts:
                for part in context.message.parts:
                    if hasattr(part, 'root') and hasattr(part.root, 'text'):
                        input_text += part.root.text
            
            print(f"🔧 [Executor] Input: {input_text}", flush=True)
            logger.info(f"Executing task {context.task_id}: '{input_text}'")
            
            # Build conversation history
            history = []
            if context.current_task and hasattr(context.current_task, 'artifacts'):
                for artifact in context.current_task.artifacts:
                    if hasattr(artifact, 'parts'):
                        for part in artifact.parts:
                            if hasattr(part, 'text'):
                                history.append(part.text)
            
            # Full context
            if history:
                full_input = f"Previous conversation:\n" + "\n".join(history[-6:]) + f"\n\nCurrent question: {input_text}"
            else:
                full_input = input_text
            
            # Execute agent
            result = await agent.invoke_async(full_input)
            response = result.output if hasattr(result, 'output') else str(result)
            
            logger.info(f"Agent raw response: {response[:500]}")
            
            # Parse JSON response - remove thinking and response tags
            clean_response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
            clean_response = re.sub(r'<response>|</response>', '', clean_response, flags=re.DOTALL).strip()
            
            logger.info(f"Cleaned response: {clean_response[:500]}")
            
            try:
                json_match = re.search(r'\{[^}]*"status"[^}]*"message"[^}]*\}', clean_response, re.DOTALL)
                if json_match:
                    response_json = json.loads(json_match.group())
                    status = response_json.get('status', 'completed')
                    message = response_json.get('message', clean_response)
                    logger.info(f"Parsed JSON - status: {status}, message: {message[:200]}")
                else:
                    status = 'completed'
                    message = clean_response
                    logger.info(f"No JSON found, using clean response as message")
            except Exception as e:
                logger.error(f"JSON parsing error: {e}")
                status = 'completed'
                message = clean_response
            
            # Map status to TaskState
            state_map = {
                'completed': 'completed',
                'input_required': 'input-required',
                'input-required': 'input-required',  # Support both formats
                'error': 'failed',
                'failed': 'failed'
            }
            task_state = state_map.get(status, 'completed')
            
            # Send artifact FIRST (before status)
            full_response = json.dumps({"status": status, "message": message}, ensure_ascii=False)
            print(f"🔧 [Executor] Sending artifact: {full_response[:200]}", flush=True)
            logger.info(f"Sending artifact: {full_response[:200]}")
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                artifact=Artifact(
                    artifactId=f"response-{context.task_id}",
                    parts=[TextPart(text=full_response)]
                )
            ))
            print(f"🔧 [Executor] Artifact sent", flush=True)
            logger.info("Artifact sent successfully")
            
            # Send status update AFTER artifact
            logger.info(f"Sending status update: {task_state}")
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                status=TaskStatus(state=task_state),
                final=(task_state != 'input-required')
            ))
            
        except Exception as e:
            logger.error(f"Error in GameBalanceExecutor: {e}", exc_info=True)
            
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                status=TaskStatus(state='failed'),
                final=True
            ))
            
            error_response = json.dumps({"status": "error", "message": f"오류 발생: {str(e)}"}, ensure_ascii=False)
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                artifact=Artifact(
                    artifactId=f"error-{context.task_id}",
                    parts=[TextPart(text=error_response)]
                )
            ))
    
    async def cancel(self, context: RequestContext):
        pass
