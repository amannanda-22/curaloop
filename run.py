#!/usr/bin/env python3
"""One-command launcher:  python run.py   ->  http://localhost:8000

First start seeds ~520 synthetic patients. `python run.py --reset` wipes and reseeds.
The built React app in frontend/dist is served by the same process (no Node needed to RUN it).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

if "--reset" in sys.argv:
    db = BACKEND / "curaloop.db"
    if db.exists():
        db.unlink()
        print("Database reset.")

port = int(os.getenv("PORT", "8000"))
dist = ROOT / "frontend" / "dist" / "index.html"
if not dist.exists():
    print("! frontend/dist not found. Build it once:  cd frontend && npm install && npm run build")
print(f"\n  CuraLoop  ->  http://localhost:{port}      API docs ->  http://localhost:{port}/docs\n")

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host=os.getenv("HOST", "0.0.0.0"), port=port, log_level="warning")
