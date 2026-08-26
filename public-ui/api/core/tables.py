"""Azure Table access with a swappable provider so tests run on fakes.

The public API creates and owns only the `pub*` tables. It reads `leads` and
`appversions`, and it creates NEITHER — those belong to the pipeline. Nothing
here can write to `leads`: see core/leads.py, which exposes no write path.

Row-key encoding mirrors src/agents/table_store.py (quote(id, safe="")).
"""
import contextlib
from urllib.parse import quote

from azure.data.tables import TableServiceClient, UpdateMode

from . import config

# pipeline-owned, read-only from here
TABLE_LEADS = "leads"
TABLE_VERSIONS = "appversions"

# owned by the public app
TABLE_USERS = "pubusers"
TABLE_SESSIONS = "pubsessions"
TABLE_NOTES = "pubnotes"
TABLE_SAVED = "pubsaved"
TABLE_ALERTS = "pubalerts"
TABLE_ALERTLOG = "pubalertlog"
TABLE_PUSH = "pubpush"

_PUBLIC_TABLES = (
    TABLE_USERS, TABLE_SESSIONS, TABLE_NOTES,
    TABLE_SAVED, TABLE_ALERTS, TABLE_ALERTLOG, TABLE_PUSH,
)


def encode_row_key(value: str) -> str:
    return quote(value, safe="")


class AzureTableProvider:
    def __init__(self, conn_str: str):
        self._client = TableServiceClient.from_connection_string(conn_str)
        for name in _PUBLIC_TABLES:
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


def get_entity(table: str, pk: str, rk: str) -> dict | None:
    try:
        return dict(provider().get(table).get_entity(partition_key=pk, row_key=rk))
    except Exception:
        return None


def upsert(table: str, entity: dict) -> None:
    if table in (TABLE_LEADS, TABLE_VERSIONS):
        # belt and braces: the public app must never mutate pipeline data
        raise RuntimeError(f"{table} is read-only for the public API")
    provider().get(table).upsert_entity(entity, mode=UpdateMode.MERGE)


def delete(table: str, pk: str, rk: str) -> None:
    if table in (TABLE_LEADS, TABLE_VERSIONS):
        raise RuntimeError(f"{table} is read-only for the public API")
    with contextlib.suppress(Exception):
        provider().get(table).delete_entity(partition_key=pk, row_key=rk)


def query(table: str, filter_str: str) -> list[dict]:
    return [dict(e) for e in provider().get(table).query_entities(filter_str)]


def scan(table: str) -> list[dict]:
    """Full-table read, for the few cases with no single partition to target
    (the notifier walks every user's alerts). Azure Tables rejects an empty
    filter string, so this is list_entities rather than query('')."""
    return [dict(e) for e in provider().get(table).list_entities()]
