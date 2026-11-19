import os
import sys
import tempfile
from pathlib import Path

# Isolated DB per test session - must be set BEFORE the app is imported.
_tmp = tempfile.mkdtemp(prefix="curaloop_test_")
# TEST_DATABASE_URL lets CI run the whole suite against PostgreSQL; default is an isolated SQLite file.
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import clock, seed  # noqa: E402
from app.db import SessionLocal, init_db, reset_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def seeded():
    reset_db()
    with SessionLocal() as db:
        info = seed.seed(db, n_patients=520)
        db.commit()
    return info


@pytest.fixture()
def client(seeded):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    init_db()
    with SessionLocal() as s:
        yield s


def H(role="coordinator", actor="tester"):
    return {"X-Role": role, "X-Actor": actor}
