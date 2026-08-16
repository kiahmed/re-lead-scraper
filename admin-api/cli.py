"""Admin user provisioning CLI — the ONLY way accounts are created.

Usage (via Make targets):
  python3 cli.py create <username> [--display-name NAME] [--role ROLE]
  python3 cli.py disable <username> | enable <username>
  python3 cli.py reset-password <username>
  python3 cli.py list
  python3 cli.py purge-sessions

Passwords are prompted (never argv). Set ADMIN_PASSWORD env var for
non-interactive use (local smoke tests only).
"""
import argparse
import getpass
import os
import sys
from datetime import UTC, datetime

from core import auth, tables, users
from core.http import ApiError


def _password() -> str:
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if pw:
        return pw
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Confirm:  "):
        sys.exit("passwords do not match")
    if len(pw) < 8:
        sys.exit("password must be at least 8 characters")
    return pw


def main() -> None:
    parser = argparse.ArgumentParser(prog="admin-users")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd in ("create", "disable", "enable", "reset-password"):
        p = sub.add_parser(cmd)
        p.add_argument("username")
        if cmd == "create":
            p.add_argument("--display-name", default="")
            p.add_argument("--role", default="admin")
    sub.add_parser("list")
    sub.add_parser("purge-sessions")
    sub.add_parser("service-token")
    args = parser.parse_args()

    try:
        if args.cmd == "create":
            user = users.create_user(args.username, _password(), args.display_name, args.role)
            print(f"created {user['username']} (role={user['role']})")
        elif args.cmd == "disable":
            users.set_active(args.username, False)
            print(f"disabled {args.username}")
        elif args.cmd == "enable":
            users.set_active(args.username, True)
            print(f"enabled {args.username}")
        elif args.cmd == "reset-password":
            users.set_password(args.username, _password())
            print(f"password reset for {args.username}")
        elif args.cmd == "list":
            for u in users.list_users():
                state = "active" if u["is_active"] else "DISABLED"
                print(f"{u['username']:24} {u['role']:8} {state:8} last login: {u['last_login_at'] or '—'}")
        elif args.cmd == "service-token":
            # machine credential for the scheduled purge Logic App: a login-less
            # user + a 10-year session. Only the SHA-256 hash is stored.
            from core import security
            if tables.get_entity(tables.TABLE_USERS, auth.USER_PK, "scheduler") is None:
                tables.upsert(tables.TABLE_USERS, {
                    "PartitionKey": auth.USER_PK, "RowKey": "scheduler",
                    "password_hash": "", "display_name": "Scheduled purge",
                    "role": "admin", "is_active": True,
                    "failed_attempts": 0, "locked_until": "",
                    "created_at": datetime.now(UTC).isoformat(), "last_login_at": "",
                })
            token = security.new_token()
            tables.upsert(tables.TABLE_SESSIONS, {
                "PartitionKey": auth.SESSION_PK,
                "RowKey": security.token_hash(token),
                "username": "scheduler",
                "created_at": datetime.now(UTC).isoformat(),
                "last_seen_at": datetime.now(UTC).isoformat(),
                "expires_at": datetime.now(UTC).replace(year=datetime.now(UTC).year + 10).isoformat(),
            })
            print(token)
        elif args.cmd == "purge-sessions":
            now = datetime.now(UTC).isoformat()
            rows = tables.query(tables.TABLE_SESSIONS, f"PartitionKey eq '{auth.SESSION_PK}'")
            purged = 0
            for row in rows:
                if row.get("expires_at", "") <= now:
                    tables.delete(tables.TABLE_SESSIONS, auth.SESSION_PK, row["RowKey"])
                    purged += 1
            print(f"purged {purged} expired session(s) of {len(rows)}")
    except ApiError as e:
        sys.exit(f"error: {e.message}")


if __name__ == "__main__":
    main()
