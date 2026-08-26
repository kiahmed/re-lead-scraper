"""Push the public app's runtime settings from .env into the Static Web App.

The SPA is static; every secret lives server-side as an SWA application
setting, which is what the managed-functions API reads through core.config.

Only the keys listed below are pushed — the repo .env also holds pipeline and
admin credentials that have no business in this app. Values are never printed.

Usage: python3 public-ui/tools/push_settings.py [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Read from .env like everything else — nothing identifying is hardcoded in a
# public repo. Override either with an environment variable.
RESOURCE_GROUP_KEY = "AZURE_RESOURCE_GROUP"
STATIC_WEB_APP_KEY = "PUBLIC_SWA_NAME"
STATIC_WEB_APP_DEFAULT = "flynest-public"

# Everything the public API may read. Nothing else crosses over.
KEYS = [
    "AZURE_STORAGE_CONNECTION_STRING",
    "PUBLIC_SITE_URL",
    "NOTIFY_EMAIL_PROVIDER",
    "NOTIFY_FROM_EMAIL",
    "NOTIFY_FROM_NAME",
    "NOTIFY_WEBPUSH_ENABLED",
    "NOTIFY_SMS_ENABLED",
    "NOTIFY_SMS_PROVIDER",
    "ACS_CONNECTION_STRING",
    "ACS_SENDER_ADDRESS",
    "ACS_SMS_FROM_NUMBER",
    "BREVO_API_KEY",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "VAPID_PUBLIC_KEY",
    "VAPID_PRIVATE_KEY",
    "VAPID_CONTACT_EMAIL",
    "OAUTH_GOOGLE_CLIENT_ID",
    "OAUTH_GOOGLE_CLIENT_SECRET",
    "OAUTH_MICROSOFT_CLIENT_ID",
    "OAUTH_MICROSOFT_CLIENT_SECRET",
    "OAUTH_FACEBOOK_CLIENT_ID",
    "OAUTH_FACEBOOK_CLIENT_SECRET",
]

SECRET_HINTS = ("SECRET", "KEY", "PASSWORD", "CONNECTION_STRING", "TOKEN")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        sys.exit(f"no .env at {path}")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env = read_env(Path(__file__).resolve().parents[2] / ".env")
    resource_group = os.environ.get(RESOURCE_GROUP_KEY) or env.get(RESOURCE_GROUP_KEY, "")
    static_web_app = (
        os.environ.get(STATIC_WEB_APP_KEY)
        or env.get(STATIC_WEB_APP_KEY)
        or STATIC_WEB_APP_DEFAULT
    )
    if not resource_group:
        sys.exit(f"{RESOURCE_GROUP_KEY} is not set (env or .env)")
    settings = {key: env[key] for key in KEYS if env.get(key)}
    if not settings:
        sys.exit("nothing to push — none of the public keys are set in .env")

    for key in sorted(settings):
        redacted = any(hint in key for hint in SECRET_HINTS)
        print(f"  {key} = {'<hidden>' if redacted else settings[key]}")
    missing = [key for key in KEYS if key not in settings]
    if missing:
        print(f"\nnot set (the matching feature stays off): {', '.join(missing)}")

    if args.dry_run:
        print("\ndry run — nothing sent")
        return

    cmd = [
        "az", "staticwebapp", "appsettings", "set",
        "-n", static_web_app, "-g", resource_group,
        "--setting-names", *[f"{k}={v}" for k, v in settings.items()],
        "-o", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"az failed: {result.stderr.strip()[:500]}")
    applied = json.loads(result.stdout or "{}").get("properties", {})
    print(f"\npushed {len(settings)} setting(s); the app now reports {len(applied)}")


if __name__ == "__main__":
    main()
