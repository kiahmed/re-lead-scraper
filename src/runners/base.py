from abc import ABC, abstractmethod


class PipelineRunner(ABC):
    @abstractmethod
    def process(self, payload: dict) -> list[dict]:
        """Receive a webhook payload, return classified leads."""
        ...
