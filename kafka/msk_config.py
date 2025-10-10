# MSK Cluster Configuration

MSK_CLUSTER_NAME = "a2a-kafka"
MSK_CLUSTER_ARN = "arn:aws:kafka:ap-northeast-2:986930576673:cluster/a2a-kafka/118e4d56-9b98-4b8e-8b15-260077611a87-2"

# Bootstrap Servers (PLAINTEXT)
MSK_BOOTSTRAP_SERVERS = "b-3.a2akafka.79ocda.c2.kafka.ap-northeast-2.amazonaws.com:9092,b-1.a2akafka.79ocda.c2.kafka.ap-northeast-2.amazonaws.com:9092,b-2.a2akafka.79ocda.c2.kafka.ap-northeast-2.amazonaws.com:9092"

# Cluster Info
MSK_KAFKA_VERSION = "3.8.x"
MSK_BROKER_NODES = 3
MSK_REGION = "ap-northeast-2"

# Security
MSK_AUTHENTICATION = "Unauthenticated"  # No auth required
MSK_ENCRYPTION = "PLAINTEXT"  # No TLS

# Topics (to be created)
TOPICS = {
    "agent.data.requests": {"partitions": 3, "replication_factor": 2},
    "agent.data.responses": {"partitions": 3, "replication_factor": 2},
    "agent.cs.requests": {"partitions": 3, "replication_factor": 2},
    "agent.cs.responses": {"partitions": 3, "replication_factor": 2},
    "agent.balance.requests": {"partitions": 3, "replication_factor": 2},
    "agent.balance.responses": {"partitions": 3, "replication_factor": 2},
}
