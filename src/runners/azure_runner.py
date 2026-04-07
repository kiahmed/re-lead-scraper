"""
POSTs the payload to the deployed Logic App (or Azure Function) HTTP trigger.
Use this when RUN_MODE=azure — local machine acts as client only.
"""
import requests
from .base import PipelineRunner


class AzureRunner(PipelineRunner):
    def __init__(self, trigger_url: str, timeout: int = 120):
        if not trigger_url:
            raise ValueError("AZURE_LOGIC_APP_TRIGGER_URL is not set")
        self.trigger_url = trigger_url
        self.timeout = timeout

    def process(self, payload: dict) -> list[dict]:
        print(f"[azure] triggering Logic App...")
        resp = requests.post(self.trigger_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
