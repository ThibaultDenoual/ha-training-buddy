# Training Buddy for Home Assistant

[![hacs][hacs-badge]][hacs]
[![tests][tests-badge]][tests-workflow]

**Training Buddy** turns Home Assistant into a workout companion. Define
reusable **exercises**, arrange them into **rounds**, combine rounds into
**sessions**, and execute a guided workout — with progress, timers, per-exercise
statistics, and full automation support — entirely locally.

This is a little side-project, the goal is to learn to use Claude Code efficiently. So yes, it is AI-generated.

> Status: **MVP (0.1.0)**. The domain model, session engine, persistence,
> statistics, entities and services are implemented and tested. See the
> [Roadmap](#roadmap) for what's next.

---

## Features

- 🏋️ **Reusable exercise definitions** — `repetition`, `timed`, and `rest`
  types, with an architecture built to add more types later.
- 🔁 **Rounds & sessions** — the same exercise can appear in many rounds with
  different targets, without duplication. A session pairs a *warm-up* round with
  a *circuit* round that you can loop.
- ▶️ **Guided execution** — start, pause, resume, stop, skip, complete, and
  continue-circuit, all manual-confirm (timers never auto-complete an exercise).
- 💾 **Survives restarts** — the active workout (current exercise, round, loop
  count, pause state, progress) is restored after a Home Assistant restart.
- 📈 **Per-exercise statistics** — every exercise becomes its own device with
  sensors for totals, personal bests, streaks, and weekly/monthly volume.
- 🧩 **Entities & services** — sensors, binary sensors and buttons on a
  controller device, plus seven automation-callable services.
- 🖥️ **No YAML** — manage everything through the UI (config & options flows);
  all data lives in Home Assistant Storage.
- 🩺 **Diagnostics** — downloadable diagnostics for support.

---

## Installation

### HACS (recommended)

1. In HACS → **Integrations** → menu → **Custom repositories**, add
   `https://github.com/thibaultdenoual/ha-training-buddy` as an *Integration*.
2. Install **Training Buddy**.
3. Restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Training Buddy**.

### Manual

Copy `custom_components/training_buddy` into your Home Assistant
`config/custom_components/` directory and restart.

---

## Configuration

Training Buddy is a **single-instance** integration. After adding it, click
**Configure** on the integration to open the management menu:

- **Add / delete exercise** — name + type (`repetition`, `timed`, `rest`).
- **Add round** / **Add exercise to a round** — build an ordered round; the
  target is interpreted as repetitions or seconds based on the exercise type.
- **Add / delete session** — pick a warm-up round and a circuit round.

There is **no YAML configuration**; everything is stored via Home Assistant's
Storage helper.

---

## Concepts

| Concept     | What it is                                                                 |
|-------------|---------------------------------------------------------------------------|
| **Exercise**| A reusable definition (e.g. *Push-ups*). Carries **no** target.           |
| **Round Entry** | A reference to an exercise *plus* a round-specific target.             |
| **Round**   | An ordered list of round entries (e.g. *Warm-up*, *Circuit*).             |
| **Session** | A template = one warm-up round + one circuit round.                        |

### Execution model

1. The **warm-up** round runs once.
2. The **circuit** round runs once.
3. After the circuit completes, the session **pauses** (`awaiting_continue`).
4. You choose **Continue Circuit** (runs the circuit again, incrementing the
   loop count) or **Stop**.

Timed and rest exercises start a timer when they begin, but **you** confirm
completion — the timer is informational only.

---

## Examples

### Start a session from an automation

```yaml
automation:
  - alias: "Start morning workout"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: training_buddy.start_session
        data:
          session_id: "<your-session-id>"
```

> Tip: find a session's `session_id` in the integration **Diagnostics**.

### React when a timed exercise's timer elapses

```yaml
automation:
  - alias: "Beep when plank timer finishes"
    trigger:
      - platform: event
        event_type: training_buddy_timer_finished
    action:
      - service: notify.mobile_app
        data:
          message: "Time's up — confirm when you're done!"
```

### Complete the current exercise

Use the built-in **Complete Exercise** button entity, or:

```yaml
service: training_buddy.complete_exercise
data:
  reps: 22   # optional; defaults to the planned target
```

---

## Entities

**Controller device** (`Training Buddy`):

| Platform       | Entities                                                                 |
|----------------|--------------------------------------------------------------------------|
| `sensor`       | Current Exercise, Current Round, Session Progress, Circuit Loop Count, Active Session Name, Session Status |
| `binary_sensor`| Workout Active, Workout Paused                                            |
| `button`       | Start, Pause, Resume, Stop, Complete Exercise, Skip Exercise, Continue Circuit |

**Per-exercise device** (one per exercise):

- *Repetition*: Times Completed, Total Reps, Last Completed, Personal Best,
  Weekly Reps, Monthly Reps, Longest Streak.
- *Timed / Rest*: Times Completed, Last Completed, Total Duration, Longest
  Duration, Longest Streak.

---

## Services

| Service | Fields |
|---|---|
| `training_buddy.start_session` | `session_id` (required) |
| `training_buddy.pause_session` | — |
| `training_buddy.resume_session` | — |
| `training_buddy.stop_session` | — |
| `training_buddy.complete_exercise` | `reps` (optional) |
| `training_buddy.skip_exercise` | — |
| `training_buddy.continue_circuit` | — |

The integration also fires events: `training_buddy_exercise_completed`,
`training_buddy_session_changed`, `training_buddy_timer_finished`.

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the domain model, storage
model, entity model, session engine, statistics engine, and extensibility
notes. For contributor and AI-session conventions, see
[`CLAUDE.md`](CLAUDE.md).

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
ruff check custom_components tests
pytest
```

The domain core (`models.py`, `session_engine.py`, `statistics.py`) is pure
Python with **no** Home Assistant imports and is covered by fast unit tests.

---

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md) and the
[issue tracker](https://github.com/thibaultdenoual/ha-training-buddy/issues).
Highlights: multi-profile support, a Lovelace card, dashboard auto-generation,
exercise categories, weekly goals, achievements/badges, calendar & wearable
integration, statistics export, and HA `timer` entity migration.

---

## License

MIT — see [`LICENSE`](LICENSE).

[hacs]: https://github.com/hacs/integration
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[tests-badge]: https://github.com/thibaultdenoual/ha-training-buddy/actions/workflows/test.yml/badge.svg
[tests-workflow]: https://github.com/thibaultdenoual/ha-training-buddy/actions/workflows/test.yml
