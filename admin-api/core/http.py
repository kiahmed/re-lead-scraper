"""Framework-agnostic request/response shapes.

Handlers receive an ApiRequest and return (status, body) — both the Azure
Functions entry point and the Flask dev server adapt to these.
"""
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
    user: dict | None = None  # injected by the router after auth

    def header(self, name: str) -> str:
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        return ""

    def bearer_token(self) -> str:
        # X-Admin-Token first: SWA's proxy REPLACES the Authorization header
        # with its own platform token before the request reaches managed
        # functions, so Authorization is only trustworthy outside SWA (local
        # dev / standalone Function App).
        custom = self.header("X-Admin-Token").strip()
        if custom:
            return custom
        auth = self.header("Authorization")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        return ""
