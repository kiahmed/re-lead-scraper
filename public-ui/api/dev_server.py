"""Local dev server — Flask adapter over the same core handlers the Azure
Function uses. Also serves the built SPA from ../web/dist when present, so
`make pub-deploy-local` simulates the production layout.

Run: python3 dev_server.py [--port 7072]
"""
import argparse
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory

from core.http import ApiRequest
from core.routes import dispatch

DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

flask_app = Flask(__name__)


@flask_app.route("/api/<path:path>", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
def api(path: str):
    api_req = ApiRequest(
        method=request.method.upper(),
        query=dict(request.args),
        body=request.get_json(silent=True) or {},
        headers=dict(request.headers),
    )
    status, payload = dispatch(api_req, path)
    if status == 302 and api_req.redirect:
        return redirect(api_req.redirect, code=302)
    return jsonify(payload), status


@flask_app.route("/", defaults={"spa_path": ""})
@flask_app.route("/<path:spa_path>")
def spa(spa_path: str):
    if not DIST.is_dir():
        return jsonify({"error": "public-ui/web/dist not built — run `make pub-build`"}), 404
    target = DIST / spa_path
    if spa_path and target.is_file():
        return send_from_directory(DIST, spa_path)
    return send_from_directory(DIST, "index.html")  # SPA fallback


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7072)
    args = parser.parse_args()
    flask_app.run(host="127.0.0.1", port=args.port, debug=False)
