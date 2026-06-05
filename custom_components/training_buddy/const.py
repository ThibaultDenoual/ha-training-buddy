"""Constants for the Training Buddy integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "training_buddy"

# This integration is a singleton: a single config entry manages everything.
# All domain data lives in Storage, never in the config entry or YAML.
SINGLETON_ENTRY_TITLE: Final = "Training Buddy"

# --- Storage -----------------------------------------------------------------
# Three separate stores are used on purpose to isolate write-frequency
# concerns. Definitions change rarely, statistics change once per completed
# exercise, runtime state changes on every action during a workout. Keeping
# them apart avoids rewriting large blobs on every timer tick.
STORAGE_VERSION_DEFINITIONS: Final = 1
STORAGE_VERSION_STATISTICS: Final = 1
STORAGE_VERSION_RUNTIME: Final = 1

STORAGE_KEY_DEFINITIONS: Final = f"{DOMAIN}.definitions"
STORAGE_KEY_STATISTICS: Final = f"{DOMAIN}.statistics"
STORAGE_KEY_RUNTIME: Final = f"{DOMAIN}.runtime"

# --- Dispatcher signals ------------------------------------------------------
# Local push architecture: the runtime manager pushes state through a
# DataUpdateCoordinator (no polling). Structural changes (new/removed
# exercises) are announced through dispatcher signals so platforms can add or
# remove entities dynamically.
SIGNAL_EXERCISES_CHANGED: Final = f"{DOMAIN}_exercises_changed"

# --- Exercise types ----------------------------------------------------------
EXERCISE_TYPE_REPETITION: Final = "repetition"
EXERCISE_TYPE_TIMED: Final = "timed"
EXERCISE_TYPE_REST: Final = "rest"

# Types whose targets are expressed as a duration in seconds.
DURATION_EXERCISE_TYPES: Final = frozenset(
    {EXERCISE_TYPE_TIMED, EXERCISE_TYPE_REST}
)
# Types whose targets are expressed as a repetition count.
REPETITION_EXERCISE_TYPES: Final = frozenset({EXERCISE_TYPE_REPETITION})

ALL_EXERCISE_TYPES: Final = frozenset(
    {EXERCISE_TYPE_REPETITION, EXERCISE_TYPE_TIMED, EXERCISE_TYPE_REST}
)

# --- Session phases & status -------------------------------------------------
PHASE_WARMUP: Final = "warmup"
PHASE_CIRCUIT: Final = "circuit"

STATUS_IDLE: Final = "idle"
STATUS_RUNNING: Final = "running"
STATUS_PAUSED: Final = "paused"
# Circuit finished; engine waits for continue_circuit or stop.
STATUS_AWAITING_CONTINUE: Final = "awaiting_continue"
STATUS_COMPLETED: Final = "completed"

# --- Services ----------------------------------------------------------------
SERVICE_START_SESSION: Final = "start_session"
SERVICE_PAUSE_SESSION: Final = "pause_session"
SERVICE_RESUME_SESSION: Final = "resume_session"
SERVICE_STOP_SESSION: Final = "stop_session"
SERVICE_COMPLETE_EXERCISE: Final = "complete_exercise"
SERVICE_SKIP_EXERCISE: Final = "skip_exercise"
SERVICE_CONTINUE_CIRCUIT: Final = "continue_circuit"

ATTR_SESSION_ID: Final = "session_id"
ATTR_REPS: Final = "reps"

# --- Devices -----------------------------------------------------------------
CONTROLLER_DEVICE_ID: Final = "controller"
MANUFACTURER: Final = "Training Buddy"
