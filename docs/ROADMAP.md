# Training Buddy — Roadmap

Tracking labels used in the issue tracker:

- **MVP** — required for / shipped in the first usable release (0.1.x).
- **Post-MVP** — clear next steps that build directly on the MVP.
- **Nice-to-have** — valuable but not on the critical path.
- **Technical debt** — internal cleanups and migrations.

Use the matching issue templates under
[`.github/ISSUE_TEMPLATE`](../.github/ISSUE_TEMPLATE) when filing work.

---

## MVP (done / in 0.1.0)

- [x] Domain model: exercises, rounds, sessions (normalized, reference-based).
- [x] Session engine state machine (start/pause/resume/stop/skip/complete/
      continue-circuit) with plan snapshotting.
- [x] Persistence across restarts via three versioned Stores.
- [x] Statistics engine (totals, personal best, streaks, weekly/monthly).
- [x] Controller + per-exercise devices and entities.
- [x] Services + events for automations.
- [x] Config flow (singleton) + menu-driven options flow CRUD.
- [x] Diagnostics.
- [x] Unit + integration test suite, ruff-clean.

---

## Post-MVP

| Item | Label | Notes |
|---|---|---|
| **Per-session start (select entity)** | Post-MVP | Replace the "start first session" button with a `select` entity + a `Start Selected` button; today specific starts go through the service. |
| **Round entry editing & reordering** | Post-MVP | Options flow currently appends entries; add move/edit/remove. |
| **Lovelace dashboard card** | Post-MVP | Custom card consuming the coordinator snapshot view model. |
| **Dashboard auto-generation** | Post-MVP | Generate a workout view from defined sessions. |
| **Exercise categories / tags** | Post-MVP | Group exercises (push/pull/legs/core). |
| **Weekly goals** | Post-MVP | Per-exercise or per-session weekly targets + progress sensors. |
| **Personal records dashboard** | Post-MVP | Aggregated PR view across exercises. |
| **Repairs support** | Post-MVP | Surface issues (e.g. session referencing deleted round) via the Repairs API. |

---

## Nice-to-have

| Item | Label | Notes |
|---|---|---|
| **Achievements system** | Nice-to-have | Unlockable milestones from statistics. |
| **Motivational badges** | Nice-to-have | Badge sensors/attributes for streaks & PRs. |
| **Export statistics** | Nice-to-have | CSV/JSON export service. |
| **Advanced analytics** | Nice-to-have | Trends, rolling averages, volume charts. |
| **Multi-profile support** | Nice-to-have | Per-user definitions & statistics. |
| **Additional exercise types** | Nice-to-have | e.g. distance, weighted reps (engine already extensible). |

---

## Technical debt

| Item | Label | Notes |
|---|---|---|
| **HA `timer` entity migration** | Technical debt | The engine abstracts timers via `timer_ends_at`; migrate to real `timer` entities once the UX is settled. |
| **Stale exercise device cleanup** | Technical debt | Proactively remove devices/entities for deleted exercises (today relies on options-flow reload). |
| **Quality Scale checklist** | Technical debt | Track and close the HA integration quality-scale requirements. |
| **i18n** | Technical debt | Add more translations beyond `en`. |
