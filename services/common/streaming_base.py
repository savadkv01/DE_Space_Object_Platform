import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional

from services.common.logging_utils import get_logger
from services.common.kafka_client import KafkaProducerClient


class BaseStreamingProducer(ABC):
    """
    Simple streaming producer template:
    - periodically extract events from source
    - transform into messages
    - send to Kafka
    """

    def __init__(self, topic: str, poll_interval_sec: int = 60) -> None:
        self.topic = topic
        self.poll_interval_sec = poll_interval_sec
        self.kafka = KafkaProducerClient()
        self.logger = get_logger(
            self.__class__.__name__,
            extra={"component": f"streaming_producer.{topic}", "run_id": "-"},
        )

    @abstractmethod
    def extract(self) -> Any:
        ...

    @abstractmethod
    def transform(self, raw: Any) -> Iterable[Dict[str, Any]]:
        """
        Return an iterable of messages (dicts) to send to Kafka.
        Each element is a complete message payload (JSON).
        """
        ...

    @abstractmethod
    def get_key(self, msg: Dict[str, Any]) -> Optional[str]:
        """
        Optional Kafka key for partitioning. Default: None.
        """
        ...

    def run_once(self) -> int:
        raw = self.extract()
        msgs = list(self.transform(raw))
        for msg in msgs:
            key = self.get_key(msg)
            self.kafka.send(self.topic, value=msg, key=key)
        self.kafka.flush()
        self.logger.info("Produced messages", extra={"topic": self.topic, "count": len(msgs)})
        return len(msgs)

    def run_forever(self) -> None:
        self.logger.info("Starting streaming producer loop", extra={"topic": self.topic})
        while True:
            try:
                self.run_once()
            except Exception:
                self.logger.exception("Streaming producer iteration failed")
            time.sleep(self.poll_interval_sec)
