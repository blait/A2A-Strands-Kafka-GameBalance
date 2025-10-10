#!/usr/bin/env python3
"""Test Kafka A2A communication."""

import asyncio
import sys
sys.path.insert(0, '.')

from kafka.agent_registry import discover_agents
from kafka.kafka_transport import KafkaTransport
from a2a.types import Message, Part, TextPart, Role, MessageSendParams
from uuid import uuid4

async def test():
    print("🧪 Testing Kafka A2A Communication\n")
    
    # 1. Discover agents
    print("1️⃣ Discovering agents...")
    agents = await discover_agents()
    
    if not agents:
        print("❌ No agents found!")
        return
    
    for agent_id, card in agents.items():
        print(f"   ✅ Found: {card['name']} ({agent_id})")
    
    # 2. Create transport
    print("\n2️⃣ Creating Kafka transport for 'data' agent...")
    transport = KafkaTransport(target_agent_name="data")
    
    # 3. Send message
    print("\n3️⃣ Sending test message...")
    msg = Message(
        kind="message",
        role=Role.user,
        parts=[Part(TextPart(kind="text", text="테란 승률 알려줘"))],
        message_id=uuid4().hex
    )
    
    try:
        result = await transport.send_message(MessageSendParams(message=msg))
        
        print("\n4️⃣ Response received:")
        print(f"   Type: {type(result).__name__}")
        print(f"   Result: {result}")
        
        if hasattr(result, 'artifacts') and result.artifacts:
            print(f"\n   Artifacts ({len(result.artifacts)}):")
            for i, artifact in enumerate(result.artifacts):
                print(f"   Artifact {i+1}: {artifact}")
                print(f"   Parts: {artifact.parts if hasattr(artifact, 'parts') else 'N/A'}")
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await transport.close()

if __name__ == "__main__":
    asyncio.run(test())
