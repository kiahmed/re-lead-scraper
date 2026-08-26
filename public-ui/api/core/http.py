"""Framework-agnostic request/response shapes — handlers take an ApiRequest
and return (status, body). Mirrors admin-api so both entry points (Azure
Functions, Flask dev server) stay trivial adapters."""
from dataclasses import dataclass, field


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class ApiRequest:
    method: str
    path_params: dict = field(default_factory=dict)
    query: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    user: dict | None = None   # injected by the router after auth
    redirect: str = ""         # handlers set this to force a 302 (OAuth hops)

    def header(self, name: str) -> str:
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        return ""

    def bearer_token(self) -> str:
        # X-Public-Token first: SWA's proxy REPLACES Authorization with its own
        # platform token before requests reach managed functions, so
        # Authorization is only trustworthy outside SWA (local dev / standalone).
        custom = self.header("X-Public-Token").strip()
        if custom:
            return custom
        auth = self.header("Authorization")
        return auth[7:].strip() if auth.startswith("Bearer ") else ""
