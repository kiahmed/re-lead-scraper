import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import tables  # noqa: E402
from tests.fakes import FakeProvider  # noqa: E402


@pytest.fixture(autouse=True)
def fake_tables():
    provider = FakeProvider()
    tables.set_provider(provider)
    yield provider
    tables.set_provider(None)
