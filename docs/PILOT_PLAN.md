# CuraLoop 90-day pilot plan

**Purpose.** Everything CuraLoop shows today runs on synthetic data and expert-prior action effects.
The pilot exists to replace those priors with measured effects, in a real programme, with a design that
produces a defensible answer whether CuraLoop works or not.

## 1. Setting (to be confirmed with the District Medical & Health Officer)
| Item | Plan |
|---|---|
| Geography | One block cluster in Anakapalle district, Andhra Pradesh (hero scenario in the demo) |
| Sites | 1 CHC (referral facility) + 4 PHCs + their sub-centres / ASHA catchments |
| Screening programme | Existing NP-NCD population screening (oral, breast, cervical; hypertension / diabetes as add-on) |
| Users | 2-3 care coordinators, ASHAs in catchment, facility desk staff, 1 programme manager |
| Languages | Telugu, Hindi, English |

## 2. Timeline
| Weeks | Activity |
|---|---|
| 0-2 | Data-sharing agreement, consent workflow, staff training, **baseline period** (current practice measured, no CuraLoop) |
| 3-10 | **Stepped-wedge go-live**: one PHC joins every 2 weeks (4 steps). Every site is its own control before it switches |
| 11-12 | Analysis, stakeholder readout, go / no-go for scale-up |

## 3. Evaluation design
Stepped-wedge by facility: no site is denied the tool, and each site contributes pre- and post-periods, so
secular trends (festival season, campaign weeks) are not mistaken for effect.

**Primary outcome:** share of screen-positive patients who complete the confirmatory step within 30 days
(14 days for urgent cases), confirmed by the *facility* (CuraLoop only allows the facility role to close a loop).

**Secondary outcomes:** median days referral to first successful contact; no-show recovery rate; share ending
`LOST` with a documented reason; coordinator minutes per closed loop; equity gap (distance and gender strata,
the 80% rule already built into the Insights tab); messages rejected by the human approval queue.

**Sample size (two-proportion, 80% power, alpha 0.05).** From a 55% baseline (see Impact tab) detecting +10 points needs
about 370 patients per condition; allowing for clustering by site, plan for roughly **750-1,000 screen-positives**
enrolled in total. If the programme cannot generate that volume in 8 live weeks the pilot extends rather than
under-reporting uncertainty.

## 4. Success criteria (agreed before go-live)
| Result | Decision |
|---|---|
| Closure within 30 days improves >= 8 points and lower bound of the 95% interval > 0 | Scale to the district |
| Improvement positive but interval includes 0 | Extend 8 weeks, do not claim success |
| No improvement, or any safety signal | Stop, publish what was learned |

The assumed action lifts in `engine/nba.py` are then **re-estimated from pilot data** and the simulator re-run.

## 5. Safeguards
* Anything beyond acknowledgements and menus is approved by a human before it is sent (queue already built); the coordinator reviews the automatic sends daily.
* Red-flag keywords route to the facility clinician; CuraLoop never gives medical advice.
* Clinical escalation SOP and a named clinical lead at the CHC.
* Weekly review of fairness metrics; stop rule if an equity gap exceeds the 80% threshold for two consecutive weeks.
* Data stays under the district health society's control (see DATA_GOVERNANCE.md).

## 6. What we need from partners
Programme data-sharing approval, a clinical lead, WhatsApp Business API number (via an approved provider),
a list of screening camps in the window, and permission for ASHA visits to be logged in the tool.

## 7. Risks
| Risk | Mitigation |
|---|---|
| Low smartphone / WhatsApp reach | Voice-call and ASHA-visit rungs of the ladder do not depend on it |
| Staff see it as extra paperwork | Worklist replaces the register; measure minutes per closed loop |
| Screening volume too low to detect effect | Extend the live window; report intervals honestly |
| Data-protection or consent gaps | Legal review before day 0; no live data without signed agreement |
