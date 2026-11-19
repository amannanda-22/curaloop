# Business model and path to scale

> Price points below are **hypotheses to validate in the pilot**, not market facts.

## Who feels the pain, who pays
| Segment | Pain | Buying route |
|---|---|---|
| State / district health societies (NHM, NP-NCD) | People are screened, then vanish; no one owns the follow-up | Programme budget, pilot grant, then tender |
| Hospital chains and diagnostic networks | Referred patients never return, so revenue and outcomes are lost | Direct SaaS |
| NGO / CSR cancer and NCD programmes | Funders ask for outcomes, not camp counts | Grant-funded licence |

## Revenue model (hypothesis)
1. **Facility subscription**: flat monthly fee per active facility (hypothesis: Rs 2,000-5,000).
2. **Outcome-linked component** in public programmes: small fee per *facility-verified* closed loop
   (hypothesis: Rs 50-100). Aligns payment with the thing that matters and is auditable, because only the
   facility role can close a loop.
3. **Implementation and training** fee for district roll-out.

## Why the unit economics can work
* Marginal cost per patient is mostly messaging; the rule engine runs without a paid LLM, so cost does not scale with usage.
* The Planner shows the value case in the buyer's language: *more people reach care per rupee of field effort*.
* One coordinator's list scales to hundreds of cases because the worklist is prioritised, not browsed.

## Wedge, then expansion
1. **Wedge:** cancer screening follow-up (oral, breast, cervical) in one district: urgent, time-sensitive, politically visible.
2. **Expand:** hypertension and diabetes linkage (largest volume), TB contact follow-up, antenatal care visits.
3. **Platform:** FHIR R4 export and ABDM-aligned identifiers let CuraLoop sit beside existing registers rather than replace them.

## Competitive landscape (honest)
Registers and the national NCD portal record that screening happened; spreadsheets and CRMs track calls. What
is rare is a system that **refuses to call a case finished until the facility confirms it**, explains why each
patient is on top of the list, and measures whether follow-up is fair across villages and genders.
That is the product, and it is also the moat: the audited event log is the data asset.

## Deployment readiness
| Need | Status |
|---|---|
| Container image, PostgreSQL, health check | Built (Dockerfile, docker-compose, Render blueprint); full test suite passes on PostgreSQL 16 |
| Auth | Signed expiring tokens, per-role passwords, rate-limited login (`AUTH_MODE=secure`) |
| Messaging | WhatsApp Cloud API webhook with signature verification and handshake |
| Interop | FHIR R4-aligned export per journey |
| Not yet built | SSO, SMS gateway, offline mode for ASHA phones, hosted multi-tenancy, formal security audit |

## 12-month roadmap
Q1 pilot + measured effects; Q2 offline-first ASHA app and SMS gateway; Q3 second district and second condition;
Q4 state-level dashboard and ABDM integration.
