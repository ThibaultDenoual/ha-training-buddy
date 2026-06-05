"""The Training Buddy session engine.

A pure, Home-Assistant-free finite state machine that drives the execution of a
workout session. Keeping it pure means the entire workout lifecycle can be
exercised by fast unit tests without spinning up Home Assistant.

Responsibilities
----------------
* Hold the authoritative :class:`SessionState` for the single active session.
* Apply transitions (start / pause / resume / stop / complete / skip /
  continue circuit) and reject invalid ones with :class:`SessionError`.
* Emit :class:`CompletionEvent` objects when an exercise is completed so the
  statistics engine can update independently.

What it deliberately does *not* do
----------------------------------
* It does not run real timers. For duration-based exercises it records when the
  timer should end (:attr:`SessionState.timer_ends_at`). Per the product
  spec, **timer completion never auto-completes an exercise** — completion is
  always an explicit user action. The Home Assistant runtime layer schedules a
  wall-clock callback purely for UI/notifications.
* It does not touch storage or fire Home Assistant events.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .const import (
    DURATION_EXERCISE_TYPES,
    PHASE_CIRCUIT,
    PHASE_WARMUP,
    STATUS_AWAITING_CONTINUE,
    STATUS_PAUSED,
    STATUS_RUNNING,
)


class SessionError(RuntimeError):
    """Raised when an invalid transition is requested."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PlanEntry:
    """A snapshot of a resolved round entry.

    The plan is snapshotted at session start so that editing or deleting
    definitions mid-workout cannot corrupt a running session, and so the
    session can always be restored after a restart even if definitions changed.
    """

    exercise_id: str
    exercise_name: str
    exercise_type: str
    target_reps: int | None = None
    target_seconds: int | None = None

    @property
    def is_duration_based(self) -> bool:
        """Return True if this entry is measured in seconds."""
        return self.exercise_type in DURATION_EXERCISE_TYPES

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "exercise_type": self.exercise_type,
            "target_reps": self.target_reps,
            "target_seconds": self.target_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanEntry:
        """Deserialize from storage."""
        return cls(
            exercise_id=data["exercise_id"],
            exercise_name=data["exercise_name"],
            exercise_type=data["exercise_type"],
            target_reps=data.get("target_reps"),
            target_seconds=data.get("target_seconds"),
        )


@dataclass(slots=True)
class CompletionEvent:
    """Emitted when an exercise is completed (not skipped)."""

    exercise_id: str
    exercise_type: str
    reps: int | None
    seconds: int | None
    timestamp: str


@dataclass(slots=True)
class SessionState:
    """The full, serializable state of the active session."""

    session_id: str
    session_name: str
    status: str
    phase: str
    entry_index: int
    loop_count: int  # number of *completed* circuit loops
    warmup: list[PlanEntry]
    circuit: list[PlanEntry]
    started_at: str
    timer_ends_at: str | None = None
    timer_started_at: str | None = None
    paused_remaining: float | None = None

    # -- derived views --------------------------------------------------------
    @property
    def current_list(self) -> list[PlanEntry]:
        """Return the entry list for the active phase."""
        return self.warmup if self.phase == PHASE_WARMUP else self.circuit

    @property
    def current_entry(self) -> PlanEntry | None:
        """Return the current entry or None if out of range."""
        entries = self.current_list
        if 0 <= self.entry_index < len(entries):
            return entries[self.entry_index]
        return None

    @property
    def current_loop(self) -> int:
        """Return the 1-based circuit loop currently being executed.

        Returns 0 while still in the warm-up phase.
        """
        if self.phase == PHASE_WARMUP:
            return 0
        return self.loop_count + 1

    @property
    def phase_total(self) -> int:
        """Return the number of entries in the current phase."""
        return len(self.current_list)

    @property
    def progress_pct(self) -> int:
        """Return progress through the current phase as a 0-100 percentage."""
        total = self.phase_total
        if total == 0:
            return 100
        done = min(self.entry_index, total)
        return round(done / total * 100)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "status": self.status,
            "phase": self.phase,
            "entry_index": self.entry_index,
            "loop_count": self.loop_count,
            "warmup": [e.to_dict() for e in self.warmup],
            "circuit": [e.to_dict() for e in self.circuit],
            "started_at": self.started_at,
            "timer_ends_at": self.timer_ends_at,
            "timer_started_at": self.timer_started_at,
            "paused_remaining": self.paused_remaining,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        """Deserialize from storage."""
        return cls(
            session_id=data["session_id"],
            session_name=data["session_name"],
            status=data["status"],
            phase=data["phase"],
            entry_index=data["entry_index"],
            loop_count=data["loop_count"],
            warmup=[PlanEntry.from_dict(e) for e in data.get("warmup", [])],
            circuit=[PlanEntry.from_dict(e) for e in data.get("circuit", [])],
            started_at=data["started_at"],
            timer_ends_at=data.get("timer_ends_at"),
            timer_started_at=data.get("timer_started_at"),
            paused_remaining=data.get("paused_remaining"),
        )


class SessionEngine:
    """Finite state machine for the single active session."""

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        """Initialize the engine.

        Args:
            now: Optional clock callable, injected for deterministic tests.
        """
        self._now = now or _utcnow
        self._state: SessionState | None = None

    # -- introspection --------------------------------------------------------
    @property
    def state(self) -> SessionState | None:
        """Return the current session state, or None when idle."""
        return self._state

    @property
    def is_active(self) -> bool:
        """Return True if a session is loaded (running/paused/awaiting)."""
        return self._state is not None

    def load(self, state: SessionState | None) -> None:
        """Load a previously persisted state (used on restore)."""
        self._state = state

    # -- transitions ----------------------------------------------------------
    def start(
        self,
        session_id: str,
        session_name: str,
        warmup: list[PlanEntry],
        circuit: list[PlanEntry],
    ) -> None:
        """Start a new session from a snapshotted plan."""
        if self._state is not None:
            raise SessionError("A session is already active")
        if not warmup and not circuit:
            raise SessionError("Session has no exercises to run")

        phase = PHASE_WARMUP if warmup else PHASE_CIRCUIT
        self._state = SessionState(
            session_id=session_id,
            session_name=session_name,
            status=STATUS_RUNNING,
            phase=phase,
            entry_index=0,
            loop_count=0,
            warmup=warmup,
            circuit=circuit,
            started_at=self._now().isoformat(),
        )
        self._begin_current_entry()

    def complete_exercise(self, reps: int | None = None) -> CompletionEvent:
        """Complete the current exercise and advance.

        For repetition exercises, ``reps`` overrides the planned target if
        provided. For duration exercises the actual elapsed time is recorded
        (falling back to the target if the timer was never started).
        """
        state = self._require_running()
        entry = state.current_entry
        if entry is None:
            raise SessionError("No current exercise to complete")

        event = self._build_completion_event(entry, reps)
        self._advance()
        return event

    def skip_exercise(self) -> None:
        """Skip the current exercise without recording a completion."""
        self._require_running()
        self._advance()

    def pause(self) -> None:
        """Pause a running session, freezing any active timer."""
        state = self._require_state()
        if state.status != STATUS_RUNNING:
            raise SessionError("Session is not running")
        state.status = STATUS_PAUSED
        if state.timer_ends_at is not None:
            ends = datetime.fromisoformat(state.timer_ends_at)
            remaining = (ends - self._now()).total_seconds()
            state.paused_remaining = max(0.0, remaining)

    def resume(self) -> None:
        """Resume a paused session, restoring any frozen timer."""
        state = self._require_state()
        if state.status != STATUS_PAUSED:
            raise SessionError("Session is not paused")
        state.status = STATUS_RUNNING
        if state.paused_remaining is not None:
            now = self._now()
            state.timer_started_at = now.isoformat()
            state.timer_ends_at = (
                now + timedelta(seconds=state.paused_remaining)
            ).isoformat()
            state.paused_remaining = None

    def continue_circuit(self) -> None:
        """Start another circuit loop after the circuit completed."""
        state = self._require_state()
        if state.status != STATUS_AWAITING_CONTINUE:
            raise SessionError("Session is not awaiting circuit continuation")
        state.phase = PHASE_CIRCUIT
        state.entry_index = 0
        state.status = STATUS_RUNNING
        self._begin_current_entry()

    def stop(self) -> None:
        """Stop and clear the active session."""
        self._require_state()
        self._state = None

    # -- internals ------------------------------------------------------------
    def _require_state(self) -> SessionState:
        if self._state is None:
            raise SessionError("No active session")
        return self._state

    def _require_running(self) -> SessionState:
        state = self._require_state()
        if state.status != STATUS_RUNNING:
            raise SessionError("Session is not running")
        return state

    def _begin_current_entry(self) -> None:
        """Set up timer bookkeeping for the current entry."""
        state = self._require_state()
        entry = state.current_entry
        state.paused_remaining = None
        if (
            entry is not None
            and entry.is_duration_based
            and entry.target_seconds
        ):
            now = self._now()
            state.timer_started_at = now.isoformat()
            state.timer_ends_at = (
                now + timedelta(seconds=entry.target_seconds)
            ).isoformat()
        else:
            state.timer_started_at = None
            state.timer_ends_at = None

    def _advance(self) -> None:
        """Advance the cursor, handling phase and loop transitions."""
        state = self._require_state()
        state.entry_index += 1

        if state.entry_index < len(state.current_list):
            self._begin_current_entry()
            return

        # End of the current phase.
        if state.phase == PHASE_WARMUP:
            if state.circuit:
                state.phase = PHASE_CIRCUIT
                state.entry_index = 0
                self._begin_current_entry()
            else:
                # Warm-up only session: nothing left to do.
                self._state = None
            return

        # End of a circuit loop.
        state.loop_count += 1
        state.status = STATUS_AWAITING_CONTINUE
        state.timer_started_at = None
        state.timer_ends_at = None

    def _build_completion_event(
        self, entry: PlanEntry, reps: int | None
    ) -> CompletionEvent:
        state = self._require_state()
        timestamp = self._now().isoformat()
        if entry.is_duration_based:
            seconds = entry.target_seconds
            if state.timer_started_at is not None:
                started = datetime.fromisoformat(state.timer_started_at)
                elapsed = (self._now() - started).total_seconds()
                if elapsed > 0:
                    seconds = round(elapsed)
            return CompletionEvent(
                exercise_id=entry.exercise_id,
                exercise_type=entry.exercise_type,
                reps=None,
                seconds=seconds,
                timestamp=timestamp,
            )
        return CompletionEvent(
            exercise_id=entry.exercise_id,
            exercise_type=entry.exercise_type,
            reps=reps if reps is not None else entry.target_reps,
            seconds=None,
            timestamp=timestamp,
        )
