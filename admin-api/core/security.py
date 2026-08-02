"""Password hashing (stdlib scrypt) and session token primitives.

Hash format: scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64> — parameters stored
per-hash so they can be raised later without breaking existing users.
"""
import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1
_SALT_BYTES = 16
_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return "$".join([
        "scrypt", str(_N), str(_R), str(_P),
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    ])


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p),
            dklen=len(base64.b64decode(hash_b64)),
        )
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
