"""Operator CLI for the public app.

Usage (via Make targets):
  python3 cli.py migrate            ensure the pub* tables exist
  python3 cli.py vapid-keys         generate the Web Push key pair (once)
  python3 cli.py service-token      mint the notifier's machine token
  python3 cli.py run-alerts [--dry-run]
  python3 cli.py list-users
  python3 cli.py disable <email> | enable <email>
  python3 cli.py purge-sessions
"""
import argparse
import base64
import json
import sys
from datetime import UTC, datetime, timedelta

from core import alerts, auth, digest, oauth, security, tables
from core.http import ApiError
from core.routes import SERVICE_ACCOUNT


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _vapid_keys() -> tuple[str, str]:
    """A P-256 pair in the raw base64url form both pywebpush and the browser's
    PushManager expect. Generated locally — the private key never leaves here."""
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    private = ec.generate_private_key(ec.SECP256R1())
    numbers = private.private_numbers()
    public = private.public_key().public_numbers()
    private_raw = numbers.private_value.to_bytes(32, "big")
    public_raw = b"\x04" + public.x.to_bytes(32, "big") + public.y.to_bytes(32, "big")
    return b64(public_raw), b64(private_raw)


def _mint_service_token() -> str:
    """A login-less account plus a long-lived session, exactly like the admin
    purge sweep's. Only the SHA-256 hash is stored."""
    if tables.get_entity(tables.TABLE_USERS, auth.USER_PK, SERVICE_ACCOUNT) is None:
        tables.upsert(tables.TABLE_USERS, {
            "PartitionKey": auth.USER_PK, "RowKey": SERVICE_ACCOUNT,
            "password_hash": "", "display_name": "Alert notifier",
            "email_verified": False, "providers": "[]",
            "phone": "", "phone_verified": False, "tz": "UTC",
            "is_active": True, "failed_attempts": 0, "locked_until": "",
            "created_at": _now(), "last_login_at": "",
        })
    token = security.new_token()
    tables.upsert(tables.TABLE_SESSIONS, {
        "PartitionKey": auth.SESSION_PK,
        "RowKey": security.token_hash(token),
        "email": SERVICE_ACCOUNT,
        "created_at": _now(), "last_seen_at": _now(),
        "expires_at": (datetime.now(UTC) + timedelta(days=3650)).isoformat(),
    })
    return token


def main() -> None:
    parser = argparse.ArgumentParser(prog="public-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("vapid-keys")
    sub.add_parser("service-token")
    sub.add_parser("list-users")
    sub.add_parser("purge-sessions")
    run = sub.add_parser("run-alerts")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--limit", type=int, default=0)
    for cmd in ("disable", "enable"):
        sub.add_parser(cmd).add_argument("email")

    args = parser.parse_args()
    try:
        if args.cmd == "migrate":
            tables.provider()
            print("public tables ensured: " + ", ".join(tables._PUBLIC_TABLES))

        elif args.cmd == "vapid-keys":
            public, private = _vapid_keys()
            print("Add these to .env (and to the SWA app settings):\n")
            print(f"VAPID_PUBLIC_KEY={public}")
            print(f"VAPID_PRIVATE_KEY={private}")
            print("\nThe public key is safe to ship to the browser; the private key is not.")

        elif args.cmd == "service-token":
            print(_mint_service_token())

        elif args.cmd == "run-alerts":
            report = digest.run(limit_alerts=args.limit, dry_run=args.dry_run)
            print(json.dumps(report, indent=2, default=str))

        elif args.cmd == "list-users":
            rows = tables.query(tables.TABLE_USERS, f"PartitionKey eq '{auth.USER_PK}'")
            for row in sorted(rows, key=lambda r: r.get("RowKey", "")):
                user = auth.public_user(row)
                state = "active" if row.get("is_active", True) else "DISABLED"
                verified = "verified" if user["email_verified"] else "unverified"
                providers = ",".join(p["provider"] for p in user["providers"]) or "password"
                alert_count = len(alerts.list_for_user(user["email"]))
                print(f"{user['email']:36} {state:9} {verified:10} {providers:22} "
                      f"{alert_count} alert(s)  last login: {user['last_login_at'] or '—'}")

        elif args.cmd in ("disable", "enable"):
            email = auth.normalize_email(args.email)
            if auth.get_user_row(email) is None:
                sys.exit(f"no such user: {email}")
            tables.upsert(tables.TABLE_USERS, {
                "PartitionKey": auth.USER_PK, "RowKey": email,
                "is_active": args.cmd == "enable",
            })
            print(f"{args.cmd}d {email}")

        elif args.cmd == "purge-sessions":
            now = _now()
            rows = tables.query(tables.TABLE_SESSIONS, f"PartitionKey eq '{auth.SESSION_PK}'")
            purged = sum(
                1 for row in rows
                if row.get("expires_at", "") <= now
                and not tables.delete(tables.TABLE_SESSIONS, auth.SESSION_PK, row["RowKey"])
            )
            states = oauth.purge_expired_states()
            print(f"purged {purged} expired session(s) of {len(rows)}, {states} stale oauth state(s)")

    except ApiError as e:
        sys.exit(f"error: {e.message}")


if __name__ == "__main__":
    main()
