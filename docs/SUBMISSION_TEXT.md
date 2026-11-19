# Text for the Hack2Skill form

## Solution summary (limit 2000)

CuraLoop closes the gap between a positive screening and confirmed care. In many programmes a person is screened, referred, and then disappears: the register records the screening, nobody owns what happens next, and the case is quietly counted as done. CuraLoop gives every screen-positive person a tracked journey (screened, referred, contacted, scheduled, attended, closed) and enforces one rule: only the receiving facility can close a loop, so "referred" is never mistaken for "treated".

For care coordinators it produces a daily worklist ranked by an explainable priority score, where every point is shown, with the reason each patient is overdue and a barrier-aware next action (transport, cost, fear, work, wrong number) on an escalation ladder from WhatsApp to call to ASHA home visit. A multilingual outreach agent (Telugu, Hindi, English) reads patient replies, detects barriers, honours STOP, routes red-flag symptoms to a clinician with a fixed safety message, and keeps anything risky in a human approval queue. It gives no medical advice.

For programme managers it adds survival analysis of time-to-care, process mining of where patients actually get stuck, a fairness audit by distance and gender, a capacity optimiser that decides who gets a call or an ASHA visit today, and an impact model that states how much of the gain survives if our assumptions are wrong.

Built for deployment: role-based access, signed-token login, audit log, FHIR R4-aligned export, WhatsApp Cloud API webhook, de-identified export, PostgreSQL support and a 90-day stepped-wedge pilot plan for one block cluster in Anakapalle, Andhra Pradesh. All data in this submission is synthetic and declared as such.

## What has been built during the challenge? (limit 1500)

Working full-stack prototype: FastAPI backend with state machine, SLA and care-gap engine, priority scoring, next-best-action ladder, multilingual rule-based outreach agent with approval queue, MILP capacity optimiser, Monte Carlo what-if and impact model, Kaplan-Meier survival, process mining, fairness audit, FHIR export, audit log, consent and opt-out handling, signed-token authentication. React and TypeScript interface with worklist, patient journey, WhatsApp-style simulator, facility desk, insights, impact and planner, rules editor and a guided demo of one patient's journey.

Evidence it works: 88 automated tests passing on SQLite and on PostgreSQL 16, covering the closed-loop rule, role permissions, optimiser versus first-come-first-served, recovery of planted patterns in synthetic data, and security. Synthetic cohort of 520 patients over 150 days. Packaged with Docker, a Render blueprint and a Vercel config.

Not built yet: real patient data, SSO, offline mode for ASHA phones, SMS gateway, clinical validation. Action effect sizes are expert assumptions that the pilot is designed to measure.

## Dropdowns

- Challenge: [Population Health] Closing the Screening-to-Care Loop
- Solution stage: Prototype
- Technology type: AI agent, Machine learning, Software application, Analytics
- Software or hardware: Software
- Conflict of interest: tick only what is true for your team (most teams: None)
- Prototype link: your Vercel URL (backup: Render URL)
- Demo video link: YouTube (unlisted is fine), under 3 minutes
- Solution deck: PDF under 5 MB made from the Hack2Skill template
