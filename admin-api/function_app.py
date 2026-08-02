"""Azure Functions entry point — one catch-all HTTP route delegating to
core.routes.dispatch. Production deploy target; local dev uses dev_server.py."""
import json

import azure.functions as func

from core.http import ApiRequest
from core.routes import dispatch

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="{*path}", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
def api(req: func.HttpRequest) -> func.HttpResponse:
    path = req.route_params.get("path", "")
    if path.startswith("api/"):
        path = path[4:]
    try:
        body = req.get_json() if req.get_body() else {}
    except ValueError:
        body = {}
    api_req = ApiRequest(
        method=req.method.upper(),
        query=dict(req.params),
        body=body if isinstance(body, dict) else {},
        headers=dict(req.headers),
    )
    status, payload = dispatch(api_req, path)
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
