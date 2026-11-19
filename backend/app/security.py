"""Authentication + hardening.

Two modes (env `AUTH_MODE`):
  demo   (default) - zero-setup local/demo run. The `X-Role` header selects the role, so the
                     jury can switch roles in one click. NEVER use for real patient data.
  secure           - signed, expiring bearer tokens from /api/auth/login. `X-Role` is ignored.
                     Passwords come from env (CURALOOP_PW_<ROLE>) and are required at startup.

Tokens are HMAC-SHA256 signed (stdlib only, no extra dependency); passwords are compared with
PBKDF2 + constant-time compare; login is rate limited per client.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque

AUTH_MODE = os.getenv("AUTH_MODE", "demo").lower()
SECURE = AUTH_MODE == "secure"
TOKEN_TTL_S = int(os.getenv("TOKEN_TTL_HOURS", "8")) * 3600
ROLES = ("coordinator", "facility", "manager")

_SECRET = os.getenv("SECRET_KEY") or secrets.token_hex(32)
if SECURE and not os.getenv("SECRET_KEY"):
    raise RuntimeError("AUTH_MODE=secure requires SECRET_KEY (use: python -c 'import secrets;print(secrets.token_hex(32))')")

_SALT = b"curaloop-v1"


def _hash(pw: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), _SALT, 120_000)


def _load_users() -> dict[str, tuple[str, bytes]]:
    """username -> (role, pbkdf2 hash). Usernames equal role names in this build."""
    users: dict[str, tuple[str, bytes]] = {}
    for role in ROLES:
        pw = os.getenv(f"CURALOOP_PW_{role.upper()}")
        if pw is None and not SECURE:
            pw = "demo"                       # demo mode only
        if pw:
            users[role] = (role, _hash(pw))
    if SECURE and len(users) < len(ROLES):
        missing = [r for r in ROLES if r not in users]
        raise RuntimeError(f"AUTH_MODE=secure requires CURALOOP_PW_<ROLE> for: {', '.join(missing)}")
    return users


USERS = _load_users()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(role: str, actor: str) -> str:
    body = _b64(json.dumps({"r": role, "a": actor, "exp": int(time.time()) + TOKEN_TTL_S}).encode())
    sig = _b64(hmac.new(_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        body, sig = token.split(".", 1)
        good = _b64(hmac.new(_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(_unb64(body))
        if data["exp"] < time.time() or data["r"] not in ROLES:
            return None
        return data
    except Exception:
        return None


def check_login(username: str, password: str) -> str | None:
    rec = USERS.get(username.lower())
    cand = _hash(password)
    if rec is None:
        hmac.compare_digest(cand, cand)       # keep timing similar
        return None
    return rec[0] if hmac.compare_digest(rec[1], cand) else None


# --- tiny in-memory login rate limiter (per client key) ------------------------------------
_ATTEMPTS: dict[str, deque] = defaultdict(deque)
MAX_ATTEMPTS, WINDOW_S = 8, 300


def rate_limited(key: str) -> bool:
    now = time.time()
    q = _ATTEMPTS[key]
    while q and q[0] < now - WINDOW_S:
        q.popleft()
    return len(q) >= MAX_ATTEMPTS


def record_attempt(key: str) -> None:
    _ATTEMPTS[key].append(time.time())


# paths reachable without a token in secure mode
PUBLIC_PREFIXES = ("/api/health", "/api/auth/login", "/api/webhooks/", "/api/meta/public")
