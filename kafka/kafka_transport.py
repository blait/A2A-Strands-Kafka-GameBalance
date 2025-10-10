import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from a2a.client.middleware import ClientCallContext, ClientCallInterceptor
from a2a.client.transports.base import ClientTransport
from a2a.types import (
    AgentCard,
    GetTaskPushNotificationConfigParams,
    Message,
    MessageSendParams,
    Task,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TaskStatusUpdateEvent,
)

logger = logging.getLogger(__name__)


class KafkaTransport(ClientTransport):
    """Kafka-based transport for A2A protocol."""

    def __init__(
        self,
        target_agent_name: str,
        bootstrap_servers: str = "localhost:9092",
        agent_card: AgentCard | None = None,
        interceptors: list[ClientCallInterceptor] | None = None,
    ):
        self.target_agent_name = target_agent_name
        self.bootstrap_servers = bootstrap_servers
        self.agent_card = agent_card
        self.interceptors = interceptors or []
        self.producer = None
        self.consumer = None
        self._pending_responses = {}  # correlation_id -> asyncio.Queue
        self._consumer_task = None

    async def _ensure_started(self):
        """Ensure Kafka producer and consumer are started."""
        if self.producer is None:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self.producer.start()
            logger.info(f"Kafka producer started for {self.target_agent_name}")

        if self.consumer is None:
            self.consumer = AIOKafkaConsumer(
                f"agent.{self.target_agent_name}.responses",
                bootstrap_servers=self.bootstrap_servers,
                value_deserializer=lambda v: json.loads(v.decode()),
                group_id=f"client-{uuid4().hex[:8]}",
            )
            await self.consumer.start()
            self._consumer_task = asyncio.create_task(self._consume_responses())
            logger.info(f"Kafka consumer started for {self.target_agent_name}")

    async def _consume_responses(self):
        """Background task to consume responses from Kafka."""
        try:
            async for msg in self.consumer:
                correlation_id = msg.key.decode()
                logger.info(f"📨 [Transport] Received response for correlation_id={correlation_id}")
                print(f"📨 [Transport] Received response for {correlation_id}", flush=True)
                if correlation_id in self._pending_responses:
                    await self._pending_responses[correlation_id].put(msg.value)
                    logger.info(f"✅ [Transport] Put response in queue for {correlation_id}")
                else:
                    logger.warning(f"⚠️ [Transport] No pending request for {correlation_id}")
        except Exception as e:
            logger.error(f"Error in response consumer: {e}")

    async def _apply_interceptors(
        self,
        method_name: str,
        request_payload: dict[str, Any],
        context: ClientCallContext | None,
    ) -> dict[str, Any]:
        """Apply interceptors to the request."""
        final_payload = request_payload
        for interceptor in self.interceptors:
            final_payload, _ = await interceptor.intercept(
                method_name, final_payload, {}, context
            )
        return final_payload

    async def send_message(
        self,
        request: MessageSendParams,
        *,
        context: ClientCallContext | None = None,
    ) -> Task | Message:
        """Sends a non-streaming message request to the agent."""
        await self._ensure_started()
        correlation_id = str(uuid4())
        response_queue = asyncio.Queue()
        self._pending_responses[correlation_id] = response_queue

        # Convert to dict for serialization
        payload = {
            "method": "send_message",
            "params": {
                "message": request.message.model_dump() if hasattr(request.message, 'model_dump') else request.message.__dict__
            }
        }
        payload = await self._apply_interceptors("send_message", payload, context)

        await self.producer.send(
            f"agent.{self.target_agent_name}.requests",
            key=correlation_id.encode(),
            value=payload,
        )

        try:
            response = await asyncio.wait_for(response_queue.get(), timeout=40.0)
        finally:
            del self._pending_responses[correlation_id]
        
        if "error" in response:
            raise Exception(f"Agent error: {response['error']}")
        
        # Check kind to determine type
        if response.get("kind") == "task" or "task_id" in response:
            return Task(**response)
        else:
            return Message(**response)

    async def send_message_streaming(
        self,
        request: MessageSendParams,
        *,
        context: ClientCallContext | None = None,
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent]:
        """Sends a streaming message request to the agent and yields responses as they arrive."""
        await self._ensure_started()
        correlation_id = str(uuid4())
        response_queue = asyncio.Queue()
        self._pending_responses[correlation_id] = response_queue

        payload = {
            "method": "send_message_streaming",
            "params": {
                "message": request.message.model_dump() if hasattr(request.message, 'model_dump') else request.message.__dict__
            }
        }
        payload = await self._apply_interceptors("send_message_streaming", payload, context)

        logger.info(f"📤 [Transport] Sending streaming request to agent.{self.target_agent_name}.requests, correlation_id={correlation_id}")
        await self.producer.send(
            f"agent.{self.target_agent_name}.requests",
            key=correlation_id.encode(),
            value=payload,
        )
        logger.info(f"✅ [Transport] Request sent, waiting for responses...")

        try:
            while True:
                logger.info(f"⏳ [Transport] Waiting for response from queue for {correlation_id}")
                response = await response_queue.get()
                logger.info(f"📦 [Transport] Got response: final={response.get('final')}, type={response.get('type')}")
                
                if response.get("error"):
                    raise Exception(f"Agent error: {response['error']}")
                
                if response.get("final"):
                    logger.info(f"🏁 [Transport] Stream completed for {correlation_id}")
                    break
                
                event_type = response.get("type")
                logger.info(f"🎯 [Transport] Yielding event type={event_type}")
                
                # Match class names from Kafka Consumer Handler
                if event_type == "Task" or event_type == "task":
                    yield Task(**response)
                elif event_type == "Message" or event_type == "message":
                    yield Message(**response)
                elif event_type == "TaskStatusUpdateEvent" or event_type == "task_status_update":
                    yield TaskStatusUpdateEvent(**response)
                elif event_type == "TaskArtifactUpdateEvent" or event_type == "task_artifact_update":
                    yield TaskArtifactUpdateEvent(**response)
        finally:
            if correlation_id in self._pending_responses:
                del self._pending_responses[correlation_id]

    async def get_task(
        self,
        request: TaskQueryParams,
        *,
        context: ClientCallContext | None = None,
    ) -> Task:
        await self._ensure_started()
        correlation_id = str(uuid4())
        response_queue = asyncio.Queue()
        self._pending_responses[correlation_id] = response_queue

        payload = {"method": "get_task", "params": request}
        payload = await self._apply_interceptors("get_task", payload, context)

        await self.producer.send(
            f"agent.{self.target_agent_name}.requests",
            key=correlation_id.encode(),
            value=payload,
        )

        try:
            response = await asyncio.wait_for(response_queue.get(), timeout=10.0)
        finally:
            del self._pending_responses[correlation_id]
        
        if "error" in response:
            raise Exception(f"Agent error: {response['error']}")
        
        return Task(**response)

    async def cancel_task(
        self,
        request: TaskIdParams,
        *,
        context: ClientCallContext | None = None,
    ) -> Task:
        await self._ensure_started()
        correlation_id = str(uuid4())
        response_queue = asyncio.Queue()
        self._pending_responses[correlation_id] = response_queue

        payload = {"method": "cancel_task", "params": request}
        payload = await self._apply_interceptors("cancel_task", payload, context)

        await self.producer.send(
            f"agent.{self.target_agent_name}.requests",
            key=correlation_id.encode(),
            value=payload,
        )

        try:
            response = await asyncio.wait_for(response_queue.get(), timeout=10.0)
        finally:
            del self._pending_responses[correlation_id]
        
        if "error" in response:
            raise Exception(f"Agent error: {response['error']}")
        
        return Task(**response)

    async def set_task_callback(
        self,
        request: TaskPushNotificationConfig,
        *,
        context: ClientCallContext | None = None,
    ) -> TaskPushNotificationConfig:
        raise NotImplementedError("set_task_callback not supported in Kafka transport")

    async def get_task_callback(
        self,
        request: GetTaskPushNotificationConfigParams,
        *,
        context: ClientCallContext | None = None,
    ) -> TaskPushNotificationConfig:
        raise NotImplementedError("get_task_callback not supported in Kafka transport")

    async def resubscribe(
        self,
        request: TaskIdParams,
        *,
        context: ClientCallContext | None = None,
    ) -> AsyncGenerator[Task | Message | TaskStatusUpdateEvent | TaskArtifactUpdateEvent]:
        raise NotImplementedError("resubscribe not supported in Kafka transport")
        return
        yield

    async def get_card(
        self,
        *,
        context: ClientCallContext | None = None,
    ) -> AgentCard:
        if self.agent_card:
            return self.agent_card
        raise NotImplementedError("get_card requires agent_card to be provided")

    async def close(self) -> None:
        """Closes the transport and cleanup resources."""
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped")
        
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")
