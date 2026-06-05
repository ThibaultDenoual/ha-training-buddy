# Training Buddy — Architecture

This document explains how the integration is structured and the reasoning
behind the key design decisions. It is the companion to [`../CLAUDE.md`](../CLAUDE.md),
which holds the contributor/AI working rules.

## Guiding principles

1. **A pure domain core.** All business logic (the domain model, the session
   state machine, and statistics aggregation) lives in modules with **zero**
   Home Assistant imports. This makes the hard parts fast to test and keeps HA
   concerns at the edges.
2. **One bridge.** A single `RuntimeManager` is the only place that wires the
   pure core to Home Assistant (storage, events, timers, the coordinator).
3. **Storage is the source of truth for data; the config entry is just "installed".**
   No domain data is kept in the config entry, and there is no YAML.

```
            ┌──────────────────────────────────────────────┐
            │                Home Assistant                 │
            │  config entry · platforms · services · flows  │
            └───────────────┬───────────────┬──────────────┘
                            │               │
                   entities (push)   services / flows
                            │               │
                    ┌───────▼───────────────▼───────┐
                    │         RuntimeManager         │  ← the only HA bridge
                    │  persistence · timer · events  │
                    └───┬─────────┬──────────┬───────┘
                        │         │          │
                ┌───────▼──┐ ┌────▼─────┐ ┌──▼────────────┐
                │ Session  │ │Statistics│ │  Definitions  │   ← pure domain
                │ Engine   │ │ Engine   │ │  (models.py)  │
                └──────────┘ └──────────┘ └───────────────┘
                        │         │          │
                    ┌───▼─────────▼──────────▼───┐
                    │   TrainingBuddyStore (3×)   │   ← HA Storage helper
                    └─────────────────────────────┘
```

## Domain model (`models.py`)

Normalized and reference-based:

- **`Exercise`** — reusable definition with a `type` (`repetition` / `timed` /
  `rest`) and **no** target. New types only require touching the small
  validation/classification helpers in `const.py` + `models.py`.
- **`RoundEntry`** — references an exercise by id and supplies the
  *round-specific* target (`target_reps` **or** `target_seconds`).
- **`Round`** — an ordered list of `RoundEntry`.
- **`Session`** — a warm-up round id + a circuit round id.
- **`Definitions`** — the aggregate root holding all of the above, with cascade
  rules (removing an exercise strips it from rounds; removing a round detaches
  it from sessions) and integrity validation.

Because entries reference exercises by id, the same exercise appears in multiple
rounds with different targets **without duplication**.

Every model is a `slots=True` dataclass with `to_dict`/`from_dict` for storage.

## Session engine (`session_engine.py`)

A pure finite state machine over a serializable `SessionState`.

**Statuses:** `running` → `paused` → `running`, `running` → `awaiting_continue`
(circuit finished) → `running` (continue) ; `stop` clears to idle.

**Plan snapshotting.** When a session starts, the resolved entries are
snapshotted into `SessionState` as `PlanEntry` lists (warm-up + circuit). This
is deliberate:

- Editing or deleting definitions mid-workout cannot corrupt a running session.
- The session can be restored after a restart even if definitions changed.

**Cursor & loops.** `phase` + `entry_index` is the cursor; `loop_count` counts
*completed* circuit loops. `current_loop` is `loop_count + 1` during the circuit
(and `0` during warm-up).

**Timers are informational.** For duration exercises the engine records
`timer_started_at` / `timer_ends_at`. It never auto-advances — completion is
always explicit (`complete_exercise`). Pause freezes the remaining time;
resume restores it.

**Clock injection.** The engine takes a `now` callable so tests are
deterministic; the runtime injects `homeassistant.util.dt.utcnow`.

## Statistics engine (`statistics.py`)

Folds `CompletionEvent`s into per-exercise `ExerciseStats`.

- **Incremental aggregates** (counters, maxima, streaks) are updated in place —
  no unbounded completion log is needed for them.
- **Windowed metrics** (weekly/monthly volume) are computed on read from a
  short rolling `history` (pruned to ~40 days), so they are always correct
  relative to "now".
- Streaks are tracked incrementally by comparing calendar-day gaps.

Extending statistics: add an aggregate field + update `apply`, or add a windowed
helper that sums over `history`.

## Storage model (`storage.py`)

`TrainingBuddyStore` wraps **three** `Store` instances, each independently
versioned with its own migration hook:

| Store         | Key                          | Write frequency        |
|---------------|------------------------------|------------------------|
| definitions   | `training_buddy.definitions` | rare (edits only)      |
| statistics    | `training_buddy.statistics`  | once per completion    |
| runtime       | `training_buddy.runtime`     | every workout action   |

They are split so that frequent runtime writes during a workout don't rewrite
the (potentially large) definitions or statistics blobs. Migrations branch on
`old_major_version` inside each store's `_async_migrate_func`.

## Coordinator (`coordinator.py`) — a deliberate non-poller

This integration has **no external data to poll**; state changes are local and
user-driven. We still use a `DataUpdateCoordinator`, but with
`update_interval=None`: it is a **push hub**. The `RuntimeManager` calls
`async_set_updated_data(snapshot)` after every change, and entities subscribe
via `CoordinatorEntity` for free listener management. This is an idiomatic
local-push pattern and avoids hand-rolling dispatcher plumbing for state
updates. (Structural changes — new exercises — *do* use a dispatcher signal, see
below.)

## Entity model (`entity.py`, `sensor.py`, `binary_sensor.py`, `button.py`)

- **Controller device** hosts the live session entities (sensors, binary
  sensors, buttons). These read the coordinator snapshot.
- **One device per exercise** hosts statistics sensors, linked to the controller
  via `via_device`. Stat sensors read the statistics engine and compute windowed
  values against `utcnow()` at read time.
- **Dynamic exercises.** When an exercise is added, `RuntimeManager` sends the
  `training_buddy_exercises_changed` dispatcher signal; the sensor platform adds
  the new exercise's device/sensors without a reload. Bulk edits via the options
  flow trigger a full reload to keep the registries tidy.

All entities use `has_entity_name = True` and stable `unique_id`s
(`training_buddy_<key>` for the controller, `training_buddy_<exercise_id>_<key>`
for stats), so they are entity- and device-registry compliant.

## Services & flows

- **Services** (`services.py`) are registered at the domain level and delegate
  to the runtime manager; invalid transitions raise `ServiceValidationError`.
- **Config flow** is a singleton (`single_config_entry` in the manifest) that
  just creates the entry.
- **Options flow** is a menu-driven CRUD over exercises/rounds/sessions that
  reads/writes the runtime manager (and therefore Storage) directly.

## Future extensibility

- **New exercise types** — extend `const.ALL_EXERCISE_TYPES` and the
  duration/repetition classification sets; the engine and stats branch on those.
- **New statistics** — see the statistics section above.
- **Multiple profiles** — `Definitions` and the stores are already namespaced
  objects; a profile dimension can be added as a keying layer.
- **HA `timer` entities** — the engine's timer fields are abstracted; migrating
  to real `timer` entities is a runtime-layer change (roadmap item).
- **Frontend card** — the coordinator snapshot is a stable view model that a
  custom Lovelace card can consume directly.
