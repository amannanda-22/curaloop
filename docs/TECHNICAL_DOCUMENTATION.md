# CuraLoop technical documentation

## 1. Problem
People who screen positive are often never confirmed at a facility. Registers record the screening and the
referral, but nobody owns the gap between them. CuraLoop makes that gap visible, ranks it, and refuses to call a case
finished until the receiving facility says so.

## 2. System overview
See `ARCHITECTURE.md` for the diagram. Single deployable: FastAPI serves the REST API and the built React app.

| Layer | Choice | Reason |
|---|---|---|
| API | FastAPI, Pydantic v2, SQLAlchemy 2 | typed, auto-documented (`/docs`) |
| Store | SQLite (zero setup) or PostgreSQL 16 (`DATABASE_URL`) | demo on a laptop, pilot on a server; test suite passes on both |
| Analytics | NumPy, SciPy, pandas | survival, MILP, Monte Carlo without heavy ML infra |
| UI | React 18, TypeScript, Tailwind v4, Vite, hand-written SVG charts | small bundle (about 75 kB gzipped JS), no charting dependency |
| Auth | HMAC-signed tokens, PBKDF2, role checks on every write | stdlib only |

## 3. Core engine
1. **State machine** (`engine/states.py`): SCREENED, REFERRED, CONTACTED, SCHEDULED, ATTENDED, CLOSED, LOST.
   `CLOSED` only via the facility outcome endpoint; `LOST` only by a manager with a reason; no-show returns to CONTACTED.
2. **SLA and gaps** (`engine/rules.py`, `gaps.py`): configurable per-state, per-urgency limits; a case is a gap when it breaches one.
3. **Priority score**: urgency, days overdue, failed attempts, barrier, distance; every point is shown to the user.
4. **Next-best-action** (`engine/nba.py`): escalation ladder SMS, call, ASHA visit, supervisor; barrier mapping picks the action that removes the stated barrier.
5. **Outreach agent** (`engine/outreach.py`): Telugu, Hindi, English; intent, barrier, red-flag and opt-out detection; approval queue.
6. **Optimizer** (`engine/allocate.py`): integer programme over calls and ASHA visits under daily capacity, compared with first-come-first-served.
7. **Simulator and impact model** (`engine/simulate.py`): Monte Carlo with common random numbers; policy comparison and effect-size sensitivity.
8. **Insights**: Kaplan-Meier with censoring, process mining (directly-follows graph, variants, conformance, bottleneck), planted-pattern recovery with confidence intervals, 80% fairness audit.
9. **Interop**: FHIR R4-aligned export per journey; WhatsApp Cloud API webhook (handshake and signature check).

## 4. API surface (selected)
`GET /api/worklist` · `GET /api/journeys/{id}` · `POST /api/journeys/{id}/{refer|contact|barrier|schedule|attend|outcome|close-lost}` ·
`POST /api/journeys/{id}/inbound` · `GET|POST /api/webhooks/whatsapp` · `GET /api/approvals` · `GET /api/facility/queue` ·
`GET /api/insights/*` · `POST /api/planner/optimize` · `POST /api/planner/simulate` · `GET /api/impact` ·
`POST /api/patients/{id}/consent` · `GET /api/export/deidentified` · `GET|PUT /api/rules` · `GET /api/audit` ·
`GET /api/fhir/journey/{id}` · `POST /api/auth/login` · `GET /api/health`. Full schema at `/docs`.

## 5. Data
Synthetic generator (`seed.py`): 520 patients, 150 days, planted effects (distance 2.5x, sex 1.5x drop-off) so analytics can be verified.
Declared in DATA_GOVERNANCE.md; no real or third-party data.

## 6. Testing
88 tests (`backend/tests`): state-machine rules, RBAC, the full hero-patient loop, optimizer never worse than first-come-first-served,
planted-pattern recovery, impact monotonicity, security (tokens, header spoofing, rate limit, webhook signatures), consent and de-identified export.
Run: `cd backend && python -m pytest -q`. Against PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest -q`.

## 7. Deployment
Docker image (multi-stage), `docker-compose.yml` (app + PostgreSQL), Render blueprint, health check at `/api/health`. See `DEPLOY.md`.
Modes: `AUTH_MODE=demo` (role switcher, public demo) and `AUTH_MODE=secure` (login required, demo tools off).

## 8. Known limits
Synthetic data; action effects are assumed until the pilot; rule-based language understanding; single-instance rate limiter;
no offline mode, SSO, or retention scheduler yet; Docker image not built in the authoring sandbox (its steps were run by hand, see DEPLOY.md).
