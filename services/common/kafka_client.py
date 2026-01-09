from dataclasses import dataclass
from typing import Any, Dict, Optional

import os
from kafka import KafkaProducer
import json


@dataclass
class KafkaConfig:
    bootstrap_servers: str
    client_id: str = "space-objects-producer"


def load_kafka_config() -> KafkaConfig:
    return KafkaConfig(
        bootstrap_servers=os.getenv("KAFKA_BROKER_URL", "kafka:9092"),
        client_id=os.getenv("KAFKA_CLIENT_ID", "space-objects-producer"),
    )


class KafkaProducerClient:
    def __init__(self, config: Optional[KafkaConfig] = None):
        cfg = config or load_kafka_config()
        self.producer = KafkaProducer(
            bootstrap_servers=cfg.bootstrap_servers.split(","),
            client_id=cfg.client_id,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
        )

    def send(self, topic: str, value: Dict[str, Any], key: Optional[str] = None) -> None:
        self.producer.send(topic, key=key, value=value)

    def flush(self) -> None:
        self.producer.flush()

    def close(self) -> None:
        self.producer.flush()
        self.producer.close()
