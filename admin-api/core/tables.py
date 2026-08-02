"""Azure Table access with a swappable provider so tests run on fakes.

Row-key encoding mirrors src/agents/table_store.py (quote(id, safe=""))
— reimplemented here on purpose so admin refactors can't break the pipeline.
"""
from urllib.parse import quote

from azure.data.tables import TableServiceClient, UpdateMode

from . import config

TABLE_LEADS = "leads"
TABLE_USERS = "users"
TABLE_SESSIONS = "sessions"
TABLE_INTERACTIONS = "interactions"
TABLE_VERSIONS = "appversions"

_ADMIN_TABLES = (TABLE_USERS, TABLE_SESSIONS, TABLE_INTERACTIONS)


def encode_row_key(lead_id: str) -> str:
    return quote(lead_id, safe="")


class AzureTableProvider:
    def __init__(self, conn_str: str):
        self._client = TableServiceClient.from_connection_string(conn_str)
        for name in _ADMIN_TABLES:
            self._client.create_table_if_not_exists(name)

    def get(self, name: str):
        return self._client.get_table_client(name)


_provider = None


def set_provider(provider) -> None:
    """Tests inject a fake provider here."""
    global _provider
    _provider = provider


def provider():
    global _provider
    if _provider is None:
        conn = config.storage_connection_string()
        if not conn:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set")
        _provider = AzureTableProvider(conn)
    return _provider


# ── thin helpers used by all domain modules ──────────────────────────────────
def get_entity(table: str, pk: str, rk: str) -> dict | None:
    try:
        return dict(provider().get(table).get_entity(partition_key=pk, row_key=rk))
    except Exception:
        return None


def upsert(table: str, entity: dict) -> None:
    provider().get(table).upsert_entity(entity, mode=UpdateMode.MERGE)


def delete(table: str, pk: str, rk: str) -> None:
    try:
        provider().get(table).delete_entity(partition_key=pk, row_key=rk)
    except Exception:
        pass


def query(table: str, filter_str: str) -> list[dict]:
    return [dict(e) for e in provider().get(table).query_entities(filter_str)]
