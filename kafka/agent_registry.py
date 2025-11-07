"""Agent Registry for dynamic agent discovery via Kafka."""

import json
import asyncio
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer


async def register_agent(agent_id: str, agent_card: dict, bootstrap_servers: str | None = None):
    """Register agent to Kafka registry."""
    if bootstrap_servers is None:
        from common.config import kafka_config
        bootstrap_servers = kafka_config.bootstrap_servers
    
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode()
    )
    await producer.start()
    
    try:
        await producer.send(
            "agent.registry",
            key=agent_id.encode(),
            value=agent_card
        )
        print(f"✅ Registered to agent.registry: {agent_id}")
    finally:
        await producer.stop()


async def discover_agents(bootstrap_servers: str | None = None, timeout: int = 5):
    """Discover all agents from Kafka registry."""
    if bootstrap_servers is None:
        from common.config import kafka_config
        bootstrap_servers = kafka_config.bootstrap_servers
    
    consumer = AIOKafkaConsumer(
        "agent.registry",
        bootstrap_servers=bootstrap_servers,
        auto_offset_reset='earliest',
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode())
    )
    await consumer.start()
    
    agents = {}
    
    try:
        # Wait for partition assignment
        await asyncio.sleep(0.5)
        
        # Seek to beginning
        for tp in consumer.assignment():
            consumer.seek(tp, 0)
        
        # Read with timeout
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                msg = await asyncio.wait_for(consumer.getone(), timeout=1.0)
                agent_id = msg.key.decode()
                agent_card = msg.value
                agents[agent_id] = agent_card
                print(f"✅ Discovered agent: {agent_id} - {agent_card.get('name', 'Unknown')}")
            except asyncio.TimeoutError:
                # No more messages
                if agents:
                    break
    except Exception as e:
        print(f"⚠️  Discovery error: {e}")
    finally:
        await consumer.stop()
    
    return agents
