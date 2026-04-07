"""
Entry point for the lead processing pipeline.
Instantiates the correct runner based on RUN_MODE.
"""
from ..config import (
    RUN_MODE,
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_THINKING_LEVEL,
    AZURE_LOGIC_APP_TRIGGER_URL,
)
from ..runners.local_runner import LocalRunner
from ..runners.azure_runner import AzureRunner


def get_runner():
    if RUN_MODE == "azure":
        return AzureRunner(trigger_url=AZURE_LOGIC_APP_TRIGGER_URL)
    return LocalRunner(gemini_api_key=GEMINI_API_KEY, gemini_model=GEMINI_MODEL, thinking_level=GEMINI_THINKING_LEVEL)


def run(payload: dict) -> list[dict]:
    return get_runner().process(payload)
