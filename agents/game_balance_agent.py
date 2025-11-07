#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
import threading
import uvicorn
import logging
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities
from common.config import agent_config

from kafka.agent_registry import register_agent
from kafka.kafka_consumer_handler import KafkaConsumerHandler
from game_balance_agent_executor import GameBalanceExecutor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('balance_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Agent Card
agent_card = AgentCard(
    name="Game Balance Agent",
    description="게임 밸런스 조정을 위한 코디네이터 에이전트",
    url=agent_config.balance_url,
    version="1.0.0",
    defaultInputModes=["text/plain"],
    defaultOutputModes=["text/plain"],
    skills=[
        AgentSkill(
            id="coordinate_balance",
            name="coordinate_balance",
            description="데이터 분석과 CS 피드백을 종합하여 밸런스 조정 제안",
            tags=[],
            input_description="밸런스 관련 질문",
            output_description="종합 분석 및 제안"
        )
    ],
    capabilities=AgentCapabilities(
        streaming=True,
        multi_turn=True
    )
)

# A2A Server
request_handler = DefaultRequestHandler(
    agent_executor=GameBalanceExecutor(),
    task_store=InMemoryTaskStore()
)

a2a_server = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler
)

app = a2a_server.build()

# Add custom streaming endpoint for GUI
from starlette.routing import Route
from starlette.responses import StreamingResponse
import json
import re
import logging

logger = logging.getLogger(__name__)

_agent_instance = None

async def ask_stream(request):
    body = await request.json()
    query = body.get('query', '')
    
    async def generate():
        try:
            global _agent_instance
            
            if _agent_instance is None:
                from game_balance_agent_executor import create_agent
                _agent_instance = await create_agent()
            
            # Stream with tool/agent info
            async for chunk in _agent_instance.stream_async(query):
                if isinstance(chunk, dict):
                    # Tool usage events
                    if 'event' in chunk:
                        event = chunk['event']
                        
                        # Tool start
                        if 'contentBlockStart' in event:
                            start = event['contentBlockStart']
                            if 'start' in start and 'toolUse' in start['start']:
                                tool_info = start['start']['toolUse']
                                tool_name = tool_info.get('name', 'unknown')
                                thinking = f"🔧 Tool: {tool_name}"
                                yield f"data: {json.dumps({'type': 'thinking', 'content': thinking}, ensure_ascii=False)}\n\n"
                    
                    # Actual text content
                    if 'data' in chunk:
                        text = chunk['data']
                        if text:
                            yield f"data: {json.dumps({'type': 'answer', 'content': text}, ensure_ascii=False)}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

app.routes.append(Route('/ask_stream', ask_stream, methods=['POST']))

if __name__ == "__main__":
    print(f"⚖️ Starting Game Balance Agent on port {agent_config.balance_port}...", flush=True)
    
    # 1. Register to Kafka registry
    async def register():
        card_dict = {
            "name": agent_card.name,
            "agent_id": "balance",
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
        await register_agent("balance", card_dict)
    
    asyncio.run(register())
    
    # 2. Start Kafka consumer in background thread
    def run_kafka_consumer():
        async def start_consumer():
            kafka_handler = KafkaConsumerHandler(
                agent_name="balance",
                agent_executor=GameBalanceExecutor(),
                task_store=InMemoryTaskStore()
            )
            await kafka_handler.start()
        
        asyncio.run(start_consumer())
    
    kafka_thread = threading.Thread(target=run_kafka_consumer, daemon=True)
    kafka_thread.start()
    print("✅ Kafka consumer started in background", flush=True)
    
    # 3. Start HTTP server
    uvicorn.run(app, host=agent_config.balance_host, port=agent_config.balance_port)
