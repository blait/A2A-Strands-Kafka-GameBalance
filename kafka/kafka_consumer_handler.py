import asyncio
import json
import logging
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import MessageSendParams, Message

logger = logging.getLogger(__name__)


class KafkaConsumerHandler:
    """Kafka Consumer that wraps DefaultRequestHandler."""

    def __init__(
        self, 
        agent_name: str, 
        agent_executor, 
        bootstrap_servers: str | None = None,
        task_store=None
    ):
        self.agent_name = agent_name
        if bootstrap_servers is None:
            from common.config import kafka_config
            bootstrap_servers = kafka_config.bootstrap_servers
        self.bootstrap_servers = bootstrap_servers
        
        # DefaultRequestHandler 재사용
        self.request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=task_store or InMemoryTaskStore()
        )
        
        self.consumer = None
        self.producer = None

    async def start(self):
        """Start consuming requests from Kafka."""
        try:
            print(f"🔄 [KafkaConsumerHandler] Creating consumer for agent.{self.agent_name}.requests...", flush=True)
            self.consumer = AIOKafkaConsumer(
                f"agent.{self.agent_name}.requests",
                bootstrap_servers=self.bootstrap_servers,
                value_deserializer=lambda v: json.loads(v.decode()),
            )
            print(f"🔄 [KafkaConsumerHandler] Starting consumer...", flush=True)
            logger.info(f"🔄 Starting consumer for agent.{self.agent_name}.requests...")
            await self.consumer.start()
            print(f"✅ [KafkaConsumerHandler] Consumer started!", flush=True)
            logger.info(f"✅ Consumer started")

            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            print(f"🔄 [KafkaConsumerHandler] Starting producer...", flush=True)
            logger.info(f"🔄 Starting producer...")
            await self.producer.start()
            print(f"✅ [KafkaConsumerHandler] Producer started!", flush=True)
            logger.info(f"✅ Producer started")

            print(f"✅ [KafkaConsumerHandler] Ready! Listening for messages...", flush=True)
            logger.info(f"✅ KafkaConsumerHandler started for agent: {self.agent_name}")
            logger.info(f"   Subscribed to: agent.{self.agent_name}.requests")

            async for msg in self.consumer:
                print(f"📨 [KafkaConsumerHandler] Received message!", flush=True)
                logger.info(f"📨 Received message: key={msg.key.decode() if msg.key else 'None'}")
                asyncio.create_task(self._handle_request(msg))
        except Exception as e:
            print(f"❌ [KafkaConsumerHandler] Error: {e}", flush=True)
            logger.error(f"❌ Error in KafkaConsumerHandler.start(): {e}", exc_info=True)

    async def _handle_request(self, msg):
        """Handle request using DefaultRequestHandler."""
        correlation_id = msg.key.decode()
        request = msg.value
        method = request.get("method")
        params = request.get("params")

        logger.info(f"📥 Handling request: method={method}, correlation_id={correlation_id}")
        print(f"📥 [Handler] method={method}, correlation_id={correlation_id}", flush=True)

        try:
            if method == "send_message":
                # DefaultRequestHandler 사용
                message = Message(**params.get("message", {}))
                result = await self.request_handler.on_message_send(
                    MessageSendParams(message=message)
                )
                
                # Task를 dict로 변환
                response = result.model_dump() if hasattr(result, 'model_dump') else result.__dict__
                await self._send_response(correlation_id, response, final=True)
                
            elif method == "send_message_streaming":
                logger.info(f"🌊 Starting streaming response for {correlation_id}")
                print(f"🌊 [Handler] Starting streaming for {correlation_id}", flush=True)
                
                # 스트리밍
                message = Message(**params.get("message", {}))
                async for event in self.request_handler.on_message_send_stream(
                    MessageSendParams(message=message)
                ):
                    event_data = event.model_dump() if hasattr(event, 'model_dump') else event.__dict__
                    event_data["type"] = event.__class__.__name__
                    print(f"📤 [Handler] Sending stream event: {str(event_data)[:100]}", flush=True)
                    await self._send_response(correlation_id, event_data, final=False)
                
                print(f"✅ [Handler] Stream completed for {correlation_id}", flush=True)
                await self._send_response(correlation_id, {"final": True}, final=True)
                
        except Exception as e:
            logger.error(f"❌ Error handling request: {e}", exc_info=True)
            await self._send_response(correlation_id, {"error": str(e)}, final=True)

    async def _send_response(self, correlation_id: str, response: dict, final: bool = False):
        """Send response to Kafka."""
        response_data = {**response, "final": final}
        print(f"📤 [KafkaConsumerHandler] Sending response", flush=True)
        print(f"   Topic: agent.{self.agent_name}.responses", flush=True)
        print(f"   correlation_id: {correlation_id}", flush=True)
        print(f"   response_data: {str(response_data)[:300]}", flush=True)
        await self.producer.send(
            f"agent.{self.agent_name}.responses",
            key=correlation_id.encode(),
            value=response_data,
        )
        print(f"✅ [KafkaConsumerHandler] Response sent", flush=True)

    async def stop(self):
        """Stop consumer and producer."""
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        logger.info(f"🛑 KafkaConsumerHandler stopped for agent: {self.agent_name}")
