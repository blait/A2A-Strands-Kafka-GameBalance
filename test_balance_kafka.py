#!/usr/bin/env python3
"""Test Balance Agent with Kafka A2A communication."""

import asyncio
import sys
sys.path.insert(0, '.')

from kafka.agent_registry import discover_agents
from kafka.kafka_transport import KafkaTransport
from a2a.types import Message, Part, TextPart, Role, MessageSendParams
from uuid import uuid4

async def test():
    print("🧪 Testing Balance Agent via Kafka\n")
    
    # 1. Discover agents
    print("1️⃣ Discovering agents...")
    agents = await discover_agents()
    
    if not agents:
        print("❌ No agents found! Make sure agents are running.")
        return
    
    for agent_id, card in agents.items():
        print(f"   ✅ Found: {card['name']} ({agent_id})")
    
    if 'balance' not in agents:
        print("\n❌ Balance agent not found! Start it first:")
        print("   python agents/game_balance_agent.py")
        return
    
    # 2. Create transport for balance agent
    print("\n2️⃣ Creating Kafka transport for 'balance' agent...")
    transport = KafkaTransport(target_agent_name="balance")
    
    # 3. Send test query
    print("\n3️⃣ Sending test query...")
    test_query = "테란과 저그의 밸런스를 분석해줘"
    
    msg = Message(
        kind="message",
        role=Role.user,
        parts=[Part(TextPart(kind="text", text=test_query))],
        message_id=uuid4().hex
    )
    
    try:
        print(f"   Query: {test_query}")
        result = await transport.send_message(MessageSendParams(message=msg))
        
        print("\n4️⃣ Response received:")
        print(f"   Type: {type(result).__name__}")
        
        if hasattr(result, 'artifacts') and result.artifacts:
            for artifact in result.artifacts:
                for part in artifact.parts:
                    if hasattr(part, 'root') and hasattr(part.root, 'text'):
                        print(f"\n   📝 Response:\n{part.root.text}\n")
                    elif hasattr(part, 'text'):
                        print(f"\n   📝 Response:\n{part.text}\n")
        
        print("✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await transport.close()

if __name__ == "__main__":
    asyncio.run(test())
