#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
import threading
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from kafka.agent_registry import register_agent
from kafka.kafka_consumer_handler import KafkaConsumerHandler
from game_balance_agent_executor import GameBalanceExecutor

# Agent Card
agent_card = AgentCard(
    name="Game Balance Agent",
    description="게임 밸런스 조정을 위한 코디네이터 에이전트",
    url="http://localhost:9001",
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

if __name__ == "__main__":
    print("⚖️ Starting Game Balance Agent on port 9001...", flush=True)
    
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
    uvicorn.run(app, host="127.0.0.1", port=9001)
