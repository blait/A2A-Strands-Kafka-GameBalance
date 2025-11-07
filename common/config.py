"""Configuration management for the game balance system."""
import os
from dataclasses import dataclass


@dataclass
class KafkaConfig:
    """Kafka connection configuration."""
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    request_timeout: float = float(os.getenv("KAFKA_REQUEST_TIMEOUT", "40.0"))
    task_timeout: float = float(os.getenv("KAFKA_TASK_TIMEOUT", "10.0"))
    
    def get_request_topic(self, agent_name: str) -> str:
        """Get request topic name for an agent."""
        return f"agent.{agent_name}.requests"
    
    def get_response_topic(self, agent_name: str) -> str:
        """Get response topic name for an agent."""
        return f"agent.{agent_name}.responses"
    
    @property
    def registry_topic(self) -> str:
        """Get registry topic name."""
        return "agent.registry"


@dataclass
class ModelConfig:
    """LLM model configuration."""
    model_id: str = os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
    temperature: float = float(os.getenv("MODEL_TEMPERATURE", "0.3"))
    region: str = os.getenv("AWS_REGION", "us-east-1")


@dataclass
class AgentConfig:
    """Agent server configuration."""
    balance_host: str = os.getenv("BALANCE_AGENT_HOST", "localhost")
    balance_port: int = int(os.getenv("BALANCE_AGENT_PORT", "9001"))
    
    data_host: str = os.getenv("DATA_AGENT_HOST", "localhost")
    data_port: int = int(os.getenv("DATA_AGENT_PORT", "9003"))
    
    cs_host: str = os.getenv("CS_AGENT_HOST", "localhost")
    cs_port: int = int(os.getenv("CS_AGENT_PORT", "9002"))
    
    @property
    def balance_url(self) -> str:
        return f"http://{self.balance_host}:{self.balance_port}"
    
    @property
    def data_url(self) -> str:
        return f"http://{self.data_host}:{self.data_port}"
    
    @property
    def cs_url(self) -> str:
        return f"http://{self.cs_host}:{self.cs_port}"


# Global config instances
kafka_config = KafkaConfig()
model_config = ModelConfig()
agent_config = AgentConfig()

