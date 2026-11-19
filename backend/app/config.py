"""Runtime configuration. Everything has a safe default so `python run.py` just works."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # .../backend
PROJECT_DIR = BASE_DIR.parent                              # .../curaloop

# SQLite by default (zero setup). For PostgreSQL:
#   DATABASE_URL=postgresql+psycopg://curaloop:curaloop@localhost:5432/curaloop
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'curaloop.db'}")
# Hosts (Render, Heroku, Railway) hand out postgres:// or postgresql:// URLs; make them use the psycopg3 driver.
for _old in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_old):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_old):]

# Built React app is served by FastAPI itself -> a single process, a single port.
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", PROJECT_DIR / "frontend" / "dist"))

# Optional. Without a key the outreach agent runs on its deterministic multilingual
# rule engine. With a key, low-confidence messages can be classified by Claude.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# WhatsApp Cloud API (all optional; without them the webhook accepts unsigned demo payloads)
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

# Demo-only tools (time machine, reset) stay off in secure mode unless explicitly allowed.
ALLOW_DEMO_TOOLS = os.getenv("ALLOW_DEMO_TOOLS", "") == "1"
