"""
Minimal auth primitives using only the Python standard library:
- PBKDF2-HMAC-SHA256 password hashing (per-user random salt)
- HMAC-signed, time-limited bearer tokens (a lightweight JWT-alike)

Kept dependency-free deliberately so the Docker image needs nothing beyond
what's already in requirements.txt.
"""
import os
import hmac
import hashlib
import base64
import json
import time
import secrets

SECRET_KEY = os.environ.get("CODEGRAPH_SECRET_KEY", "dev-secret-change-me").encode()
TOKEN_TTL_SECONDS = 12 * 60 * 60  # 12 hours


def hash_password(password: str, salt: str | None = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return base64.b64encode(digest).decode(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest, _ = hash_password(password, salt)
    return hmac.compare_digest(digest, expected_hash)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(user_id: int, username: str, role: str) -> str:
    payload = {"uid": user_id, "sub": username, "role": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = _b64url(json.dumps(payload).encode())
    sig = _b64url(hmac.new(SECRET_KEY, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str):
    try:
        body, sig = token.split(".")
        expected_sig = _b64url(hmac.new(SECRET_KEY, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(_b64url_decode(body))
        if payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


def generate_api_key() -> str:
    return "cg_" + secrets.token_urlsafe(32)
