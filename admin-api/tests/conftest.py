import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import tables
from tests.fakes import FakeProvider


@pytest.fixture(autouse=True)
def fake_tables():
    provider = FakeProvider()
    tables.set_provider(provider)
    yield provider
    tables.set_provider(None)
