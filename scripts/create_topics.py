#!/usr/bin/env python3
"""Create Kafka topics on MSK cluster."""

import sys
import os

# Get bootstrap servers from environment variable
MSK_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092"  # Default to local for development
)

# Import from kafka-python package (not local kafka folder)
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

TOPICS = {
    "agent.data.requests": {"partitions": 3, "replication_factor": 1},
    "agent.data.responses": {"partitions": 3, "replication_factor": 1},
    "agent.cs.requests": {"partitions": 3, "replication_factor": 1},
    "agent.cs.responses": {"partitions": 3, "replication_factor": 1},
    "agent.balance.requests": {"partitions": 3, "replication_factor": 1},
    "agent.balance.responses": {"partitions": 3, "replication_factor": 1},
    "agent.registry": {"partitions": 1, "replication_factor": 1},
}

def create_topics():
    """Create all required topics."""
    print(f"🔗 Connecting to Kafka: {MSK_BOOTSTRAP_SERVERS}")
    
    admin_client = KafkaAdminClient(
        bootstrap_servers=MSK_BOOTSTRAP_SERVERS,
        client_id='topic-creator'
    )
    
    # Create NewTopic objects
    new_topics = []
    for topic_name, config in TOPICS.items():
        new_topics.append(NewTopic(
            name=topic_name,
            num_partitions=config['partitions'],
            replication_factor=config['replication_factor']
        ))
    
    # Create topics
    try:
        admin_client.create_topics(new_topics=new_topics, validate_only=False)
        print("✅ Topics created successfully:")
        for topic in new_topics:
            print(f"   - {topic.name}")
    except TopicAlreadyExistsError:
        print("⚠️  Some topics already exist")
    except Exception as e:
        print(f"❌ Error creating topics: {e}")
        return False
    
    # List topics to verify
    print("\n📋 Existing topics:")
    topics = admin_client.list_topics()
    for topic in sorted(topics):
        print(f"   - {topic}")
    
    admin_client.close()
    return True

if __name__ == "__main__":
    success = create_topics()
    sys.exit(0 if success else 1)

