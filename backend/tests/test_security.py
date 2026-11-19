"""Secure-mode auth tests. Run in a subprocess-free way by reloading the security module state."""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

from app import security


def test_token_roundtrip_and_tamper():
    t = security.issue_token("manager", "PM")
    assert security.verify_token(t)["r"] == "manager"
    body, sig = t.split(".")
    assert security.verify_token(body + "." + sig[:-2] + "xx") is None
    assert security.verify_token("garbage") is None


def test_expired_token_rejected(monkeypatch):
    t = security.issue_token("manager", "PM")
    real = security.time.time
    monkeypatch.setattr(security.time, "time", lambda: real() + security.TOKEN_TTL_S + 5)
    assert security.verify_token(t) is None


def test_login_demo_mode(client):
    r = client.post("/api/auth/login", json={"username": "manager", "password": "demo"})
    assert r.status_code == 200 and r.json()["role"] == "manager"
    assert client.post("/api/auth/login", json={"username": "manager", "password": "nope"}).status_code == 401


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_login_rate_limit(client):
    security._ATTEMPTS.clear()
    for _ in range(security.MAX_ATTEMPTS):
        client.post("/api/auth/login", json={"username": "facility", "password": "bad"})
    assert client.post("/api/auth/login", json={"username": "facility", "password": "bad"}).status_code == 429
    security._ATTEMPTS.clear()


def test_secure_mode_blocks_header_spoofing(client, monkeypatch):
    monkeypatch.setattr(security, "SECURE", True)
    # no token -> 401 even with a manager header
    assert client.get("/api/worklist", headers={"X-Role": "manager"}).status_code == 401
    assert client.get("/api/health").status_code == 200                        # public
    tok = security.issue_token("coordinator", "Care coordinator")
    h = {"Authorization": f"Bearer {tok}", "X-Role": "manager"}               # spoof attempt
    assert client.get("/api/worklist", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).json()["role"] == "coordinator"
    # coordinator token cannot edit rules even while claiming manager in the header
    assert client.put("/api/rules", json={}, headers=h).status_code in (403, 422)


def test_whatsapp_signature_enforced(client, monkeypatch):
    import hashlib, hmac, json
    from app import config
    monkeypatch.setattr(config, "WHATSAPP_APP_SECRET", "s3cret")
    body = json.dumps({"junk": 1}).encode()
    assert client.post("/api/webhooks/whatsapp", content=body).status_code == 403
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    r = client.post("/api/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig})
    assert r.status_code == 200 and r.json()["status"] == "ignored"


def test_whatsapp_verify_handshake(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "WHATSAPP_VERIFY_TOKEN", "tok")
    ok = client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"}).status_code == 403


def test_demo_tools_disabled_in_secure_mode(client, monkeypatch):
    monkeypatch.setattr(security, "SECURE", True)
    h = {"Authorization": f"Bearer {security.issue_token('manager', 'PM')}"}
    assert client.post("/api/demo/reset", headers=h).status_code == 403
    assert client.post("/api/clock/advance", json={"days": 1}, headers=h).status_code == 403
