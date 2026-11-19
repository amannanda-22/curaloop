export type Role = "coordinator" | "facility" | "manager";
export type Bucket = "critical" | "high" | "medium" | "low" | "closed";

export interface Patient {
  id: number; name: string; age: number; sex: string; village: string;
  language: string; language_name: string; phone: string; abha_id: string; consent_outreach?: boolean;
}
export interface Gap { code: string; severity: number; days_overdue: number; label: string; detail: string }
export interface ScorePart { label: string; points: number }
export interface RingSeg { state: string; label: string; status: "done" | "current" | "stuck" | "todo" | "lost" }
export interface Nba {
  step: string; unit: string; channel: string; owner: string; title: string; detail: string;
  script: string | null; effect: number; why: string[]; ladder: string[];
}
export interface Appt { id: number; when: string; status: string; confirmed: boolean; facility: string }
export interface JEvent { id: number; ts: string; kind: string; from: string | null; to: string | null; channel: string | null; detail: string; actor: string }
export interface Msg {
  id: number; journey_id: number; ts: string; direction: "in" | "out"; channel: string; language: string; text: string;
  intent: string | null; barrier: string | null; status: string; flag: string | null; note: string | null;
}
export interface Card {
  id: number; patient: Patient; state: string; state_label: string; urgency: "HIGH" | "ROUTINE"; department: string;
  finding: string; facility: string | null; facility_id: number | null; distance_km: number;
  age_in_state_days: number; journey_age_days: number; sla_days: number | null;
  barrier: string | null; barrier_label: string | null;
  contact_attempts: number; failed_contacts: number; missed_appointments: number; clinical_flag: boolean;
  score: number; bucket: Bucket; score_breakdown: ScorePart[]; gaps: Gap[]; nba: Nba | null;
  appointment: Appt | null; ring: RingSeg[]; closed_at: string | null; close_reason: string | null;
  events?: JEvent[]; messages?: Msg[]; appointments?: Appt[]; screening?: { camp: string; screened_at: string; finding: string };
}
export interface Worklist { as_of: string; total: number; counts: Record<string, number>; items: Card[] }
export interface Meta {
  roles: Record<string, string>; states: { code: string; label: string }[]; barriers: Record<string, string>;
  languages: Record<string, string>; outcomes: Record<string, string>;
  facilities: { id: number; name: string; kind: string; area: string }[];
  hero_journey_id: number | null; ladder: string[]; llm_enabled: boolean;
}
export interface Summary {
  as_of: string; patients_flagged: number; referred: number; referral_rate_pct: number; loops_closed: number;
  loop_closure_rate_pct: number; attended: number; follow_up_completion_pct: number; lost: number; open: number;
  open_with_gaps: number; critical: number; missed_appointment_rate_pct: number; avg_referral_delay_days: number | null;
  median_days_to_close: number | null; sla_breaches_by_stage: Record<string, number>;
}
export interface FunnelStage { state: string; label: string; count: number; dropped: number; pct_of_prev: number; pct_of_start: number }
export interface Funnel { stages: FunnelStage[]; biggest_leak: FunnelStage | null }
export interface ProcEdge { from: string; to: string; count: number; median_days: number; back_edge: boolean; total_wait_days: number }
export interface Process {
  nodes: { state: string; count: number }[]; edges: ProcEdge[]; variants: { path: string; count: number }[];
  conformance: { journeys: number; on_ideal_path: number; with_rework_loops: number; skipped_a_step: number; ended_lost: number; fitness_pct: number };
  bottleneck: ProcEdge | null;
}
export interface Stratum { name: string; n: number; median_days: number | null; closed_by_day_30_pct: number; curve: { day: number; closed: number }[] }
export interface SurvivalRes { by: string; strata: Stratum[]; max_day: number }
export interface PatternCheck {
  name: string; group_a: string; group_b: string; rate_a_pct: number | null; rate_b_pct: number | null;
  recovered: { rr: number | null; lo: number | null; hi: number | null }; planted: number | null; status: string;
}
export interface Patterns { checks: PatternCheck[]; cohort_size: number; note: string }
export interface Fairness { groups: { dimension: string; rows: { group: string; n: number; closure_rate_pct: number; ratio_vs_best: number | null; flag: boolean }[] }[]; rule: string; cohort_size: number }
export interface FacRow { facility_id: number; name: string; kind: string; referred: number; closed: number; lost: number; open: number; closure_rate_pct: number; median_days_to_close: number | null; awaiting_outcome: number }
export interface FacRes { facilities: FacRow[]; barriers: { code: string; label: string; count: number }[] }
export interface PlanRow {
  id: number; action: string; expected_gain: number; patient: Patient; state: string; urgency: string;
  barrier_label: string | null; score: number; bucket: Bucket; headline_gap: string; nba_title: string;
}
export interface PlanRes {
  capacity: { calls: number; asha_visits: number }; candidates: number; plan: PlanRow[]; expected_extra_closures: number;
  fcfs_extra_closures: number; improvement_vs_fcfs_pct: number | null; solver: string; assumption_note: string;
}
export interface SimCurve { days: number[]; mean: number[]; p05: number[]; p95: number[]; final_mean: number }
export interface SimRes { baseline: SimCurve; scenario: SimCurve; extra_closures: number; open_journeys: number; assumption_note: string }
export interface AuditRow { id: number; ts: string; actor: string; role: string; action: string; entity: string; entity_id: number | null; detail: string }
export interface Approval extends Msg { patient: Patient; state: string; age_hours: number }
export interface Rules {
  sla_days: Record<string, Record<string, number>>; weights: Record<string, number>;
  buckets: Record<string, number>; capacity: { calls: number; asha_visits: number }; horizon_days: number;
}
export interface Clock { now: string; offset_days: number }
