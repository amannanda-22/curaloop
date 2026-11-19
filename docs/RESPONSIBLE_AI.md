# Responsible AI: model card for CuraLoop

## Intended use
Operational follow-up for screen-positive patients: who to contact next, through which channel, and why.
**Not** a diagnostic tool; produces no clinical advice, risk-of-disease score, or treatment suggestion.

## Components and how each is governed
| Component | Type | Safeguard |
|---|---|---|
| State machine and SLA engine | Deterministic rules | Only the facility can close a loop; reason required for `LOST` |
| Priority score | Transparent weighted sum | Per-point breakdown shown for every patient; weights editable by manager and audited |
| Next-best-action | Rule ladder + barrier mapping | Readable by a coordinator; no learned black box |
| Outreach agent | Rule-based intent and barrier parser (te / hi / en); optional LLM fallback only if a key is set | Red-flag template; promises, reschedules and low-confidence replies wait in a human approval queue; only acknowledgements and menus go out automatically; STOP is honoured immediately |
| Optimizer / simulator | MILP and Monte Carlo | Action lifts are **expert priors**, labelled as assumptions everywhere; sensitivity table shows results if priors are wrong |
| Survival and pattern recovery | Kaplan-Meier, risk ratios with CIs | Open cases censored, not counted as lost |

## Safety
* Messages containing red-flag symptoms (e.g. bleeding, severe pain, breathlessness) never get a templated reply; they are routed to the facility clinician.
* The agent does not answer medical questions; it states that the facility doctor will.

## Fairness
Closure rates are compared by distance band and gender with the 80% rule and confidence intervals (Insights tab). In the
synthetic data a distance gap and a gender gap were *planted*; the tool recovers them, which shows the audit can find
inequity, not that inequity exists in any real programme. A real-data audit is part of the pilot.

## Evaluation honesty
88 automated tests cover transitions, RBAC, optimizer vs first-come-first-served, planted-pattern recovery and security.
In the simulator, CuraLoop beats "nobody works the list" with a clear margin, but its edge over a manual register has an interval
that includes zero; we report that rather than hide it.

## Limitations
Synthetic data only; effect sizes are assumed; language coverage is rule-based and can misread slang or code-mixed text
(low-confidence messages go to a human); no formal clinical validation.
