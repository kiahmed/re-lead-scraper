"""
Reads and writes version records via table_store.
Computes SHA-256 hash of the classifier + outreach sections of values.yaml
to detect when the local config diverges from what was last deployed.
"""
import hashlib
import json
import yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
_VALUES_PATH = ROOT / "values.yaml"


def _load_relevant_sections() -> dict:
    """Load only the classifier and outreach sections — the parts that drive workflow JSON."""
    with open(_VALUES_PATH) as f:
        cfg = yaml.safe_load(f)
    return {
        "classifier": cfg.get("classifier", {}),
        "outreach": cfg.get("outreach", {}),
        "filter": cfg.get("filter", {}),
    }


def compute_local_hash() -> str:
    """SHA-256 of the classifier + outreach + filter sections of values.yaml."""
    sections = _load_relevant_sections()
    canonical = json.dumps(sections, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_categories() -> list[str]:
    with open(_VALUES_PATH) as f:
        cfg = yaml.safe_load(f)
    return list(cfg.get("classifier", {}).get("categories", {}).keys())


class VersionTracker:
    def __init__(self):
        # Import here to avoid circular import and to allow table_store to be optional
        from src.agents import table_store as _ts
        self._ts = _ts

    def local_hash(self) -> str:
        return compute_local_hash()

    def deployed_hash(self) -> str | None:
        record = self._ts.get_version()
        if record is None:
            return None
        return record.get("deployed_hash")

    def status(self) -> str:
        """Returns 'in-sync', 'out-of-sync', or 'never-deployed'."""
        record = self._ts.get_version()
        if record is None:
            return "never-deployed"
        return record.get("status", "out-of-sync")

    def is_in_sync(self) -> bool:
        return self.local_hash() == (self.deployed_hash() or "")

    def apply(self) -> str:
        """Write local version record to table. Returns the hash."""
        local_hash = compute_local_hash()
        categories = get_categories()
        self._ts.upsert_local_version(local_hash, categories)
        return local_hash

    def mark_deployed(self, deployed_hash: str) -> None:
        self._ts.update_deployed_version(deployed_hash)

    def report(self) -> dict:
        local = compute_local_hash()
        record = self._ts.get_version() or {}
        deployed = record.get("deployed_hash", "never")
        return {
            "local_hash": local[:12] + "...",
            "deployed_hash": (deployed[:12] + "...") if deployed != "never" else "never",
            "synced_at": record.get("synced_at", "—"),
            "deployed_at": record.get("deployed_at", "—"),
            "status": record.get("status", "never-deployed"),
            "in_sync": local == deployed,
        }
