#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uvicorn
import logging
import asyncio
from starlette.applications import Starlette
from starlette.responses import StreamingResponse
from starlette.routing import Route
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities
from cs_feedback_agent_executor import CSFeedbackExecutor, agent
from kafka.agent_registry import register_agent
from kafka.kafka_consumer_handler import KafkaConsumerHandler
import json
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent Card
agent_card = AgentCard(
    name="CS Feedback Agent",
    description="게임 포럼 고객 피드백 조회 에이전트",
    url="http://localhost:9002",
    version="1.0.0",
    defaultInputModes=["text/plain"],
    defaultOutputModes=["text/plain"],
    skills=[
        AgentSkill(
            id="get_feedback",
            name="get_feedback",
            description="게임 포럼 피드백 조회",
            tags=[],
            input_description="조회할 종족 또는 긴급도",
            output_description="피드백 목록"
        )
    ],
    capabilities=AgentCapabilities(
        streaming=True,
        multi_turn=True
    )
)

# Custom streaming endpoint
async def ask_stream(request):
    body = await request.json()
    query = body.get('query', '')
    
    async def generate():
        try:
            result = await agent.invoke_async(query)
            full_response = result.output if hasattr(result, 'output') else str(result)
            
            # Extract and send thinking
            thinking_matches = re.findall(r'<thinking>(.*?)</thinking>', full_response, re.DOTALL)
            for thinking in thinking_matches:
                yield f"data: {json.dumps({'type': 'thinking', 'content': thinking.strip()})}\n\n"
            
            # Send answer (remove thinking and response tags)
            clean_response = re.sub(r'<thinking>.*?</thinking>', '', full_response, flags=re.DOTALL)
            clean_response = re.sub(r'<response>|</response>', '', clean_response, flags=re.DOTALL).strip()
            
            if clean_response:
                yield f"data: {json.dumps({'type': 'answer', 'content': clean_response})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

# A2A Server
request_handler = DefaultRequestHandler(
    agent_executor=CSFeedbackExecutor(),
    task_store=InMemoryTaskStore()
)

a2a_server = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler
)

# Build base app
app = a2a_server.build()

# Add custom route
app.routes.append(Route('/ask_stream', ask_stream, methods=['POST']))

if __name__ == "__main__":
    logger.info("Starting CS Feedback Agent on port 9002...")
    
    import threading
    
    # 1. Register to Kafka registry
    async def register():
        card_dict = {
            "name": agent_card.name,
            "agent_id": "cs",
            "description": agent_card.description,
            "skills": [
                {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description
                }
                for skill in agent_card.skills
            ],
            "capabilities": {
                "streaming": agent_card.capabilities.streaming if agent_card.capabilities else False
            }
        }
        await register_agent("cs", card_dict)
    
    asyncio.run(register())
    
    # 2. Start Kafka consumer in background thread
    def run_kafka_consumer():
        async def start_consumer():
            kafka_handler = KafkaConsumerHandler(
                agent_name="cs",
                agent_executor=CSFeedbackExecutor(),
                task_store=InMemoryTaskStore()
            )
            await kafka_handler.start()
        
        asyncio.run(start_consumer())
    
    kafka_thread = threading.Thread(target=run_kafka_consumer, daemon=True)
    kafka_thread.start()
    logger.info("✅ Kafka consumer started in background")
    
    # 3. Start HTTP server
    uvicorn.run(app, host="0.0.0.0", port=9002)
