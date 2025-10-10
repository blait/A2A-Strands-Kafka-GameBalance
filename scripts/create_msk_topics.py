#!/usr/bin/env python3
"""Create Kafka topics on MSK cluster."""

# MSK Configuration
MSK_BOOTSTRAP_SERVERS = "b-3.a2akafka.79ocda.c2.kafka.ap-northeast-2.amazonaws.com:9092"

TOPICS = [
    "agent.data.requests",
    "agent.data.responses",
    "agent.cs.requests",
    "agent.cs.responses",
    "agent.balance.requests",
    "agent.balance.responses",
]

def create_topics():
    """Create topics using kafka-python."""
    from kafka import KafkaAdminClient
    from kafka.admin import NewTopic
    from kafka.errors import TopicAlreadyExistsError
    
    print(f"🔗 Connecting to MSK: {MSK_BOOTSTRAP_SERVERS}")
    
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=MSK_BOOTSTRAP_SERVERS,
            client_id='topic-creator',
            request_timeout_ms=10000
        )
        
        # Create NewTopic objects
        new_topics = [
            NewTopic(name=topic, num_partitions=3, replication_factor=2)
            for topic in TOPICS
        ]
        
        # Create topics
        admin_client.create_topics(new_topics=new_topics, validate_only=False)
        print("✅ Topics created successfully:")
        for topic in TOPICS:
            print(f"   - {topic}")
            
    except TopicAlreadyExistsError:
        print("⚠️  Topics already exist")
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'admin_client' in locals():
            admin_client.close()
    
    return True

if __name__ == "__main__":
    import sys
    success = create_topics()
    sys.exit(0 if success else 1)
