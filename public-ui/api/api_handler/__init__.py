"""Azure Functions entry point (v1 programming model — required because SWA
managed functions disallow the AzureWebJobsFeatureFlags setting the v2 model
needs). One catch-all HTTP route delegating to core.routes.dispatch."""
import json

import azure.functions as func

from core.http import ApiRequest
from core.routes import dispatch


def main(req: func.HttpRequest) -> func.HttpResponse:
    path = (req.route_params.get("path", "") or "").removeprefix("api/")
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
    if status == 302 and api_req.redirect:
        # OAuth hops: the browser follows these, no JSON body involved
        return func.HttpResponse(status_code=302, headers={"Location": api_req.redirect})
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
