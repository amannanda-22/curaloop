# CuraLoop architecture

```mermaid
flowchart LR
  subgraph Patient side
    P[Patient<br/>WhatsApp / SMS<br/>Telugu · Hindi · English]
  end
  subgraph Web app React + TypeScript + Tailwind
    W[Worklist] --- O[Outreach] --- F[Facility desk] --- I[Insights] --- PL[Impact & planner] --- A[Rules & audit]
  end
  subgraph FastAPI
    API[REST API + RBAC<br/>coordinator · facility · manager]
    SM[Closed-loop state machine<br/>+ SLA engine]
    GAP[Care-gap detection<br/>+ explainable priority score]
    NBA[Barrier-aware<br/>Next-Best-Action ladder]
    AG[Outreach agent<br/>intent · barrier · red-flag guardrail]
    OPT[Optimizer MILP<br/>+ what-if Monte Carlo]
    AN[Analytics: Kaplan-Meier,<br/>process mining, fairness, pattern recovery]
    FH[FHIR R4 export]
  end
  DB[(PostgreSQL / SQLite<br/>patients · journeys · events · messages · audit)]
  P <-->|webhook /api/webhooks/whatsapp| AG
  W & O & F & I & PL & A <--> API
  API --> SM --> DB
  API --> GAP & NBA & OPT & AN & FH
  AG --> SM
  GAP & NBA & OPT & AN --> DB
```

## The closed-loop rule
```
SCREENED -> REFERRED -> CONTACTED -> SCHEDULED -> ATTENDED -> CLOSED
                           ^            |
                           +-- no-show -+      (any open state -> LOST, manager only, reason required)
```
`CLOSED` is reachable only through `POST /journeys/{id}/outcome` as the **facility** role. The check is enforced twice:
at the endpoint (RBAC, 403) and inside the state machine (409). A coordinator cannot close a loop by ticking a box.

## Data model (FHIR-aligned)
Patient -> `Patient` · Journey -> `ServiceRequest` · Appointment -> `Appointment` · Event -> provenance log ·
Message -> `Communication` · next action -> `Task`. Export: `GET /api/fhir/journey/{id}`.
`events` is append-only and is the input to process mining.
