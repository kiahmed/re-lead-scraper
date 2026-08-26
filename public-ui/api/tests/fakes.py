"""In-memory fake of the table provider — mirrors the small subset of
azure-data-tables that core.tables uses."""
import re


class FakeTable:
    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}

    def get_entity(self, partition_key: str, row_key: str) -> dict:
        key = (partition_key, row_key)
        if key not in self.rows:
            raise KeyError(key)
        return dict(self.rows[key])

    def upsert_entity(self, entity: dict, mode=None) -> None:
        key = (entity["PartitionKey"], entity["RowKey"])
        merged = dict(self.rows.get(key, {}))
        merged.update(entity)
        self.rows[key] = merged

    def delete_entity(self, partition_key: str, row_key: str) -> None:
        self.rows.pop((partition_key, row_key), None)

    def query_entities(self, filter_str: str):
        m = re.match(r"PartitionKey eq '(.*)'", filter_str)
        assert m, f"fake only supports PartitionKey filters, got: {filter_str}"
        pk = m.group(1)
        return [dict(v) for (p, _), v in sorted(self.rows.items()) if p == pk]

    def list_entities(self):
        return [dict(v) for _, v in sorted(self.rows.items())]


class FakeProvider:
    def __init__(self):
        self.tables: dict[str, FakeTable] = {}

    def get(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable())
