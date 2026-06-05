"""Tests for the pure session engine state machine."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.training_buddy.const import (
    STATUS_AWAITING_CONTINUE,
    STATUS_PAUSED,
    STATUS_RUNNING,
)
from custom_components.training_buddy.session_engine import (
    PlanEntry,
    SessionEngine,
    SessionError,
    SessionState,
)


@pytest.fixture
def clock(fixed_now: datetime) -> list[datetime]:
    return [fixed_now]


@pytest.fixture
def engine(clock: list[datetime]) -> SessionEngine:
    return SessionEngine(now=lambda: clock[0])


def _warmup() -> list[PlanEntry]:
    return [
        PlanEntry("ex1", "Push-ups", "repetition", target_reps=10),
        PlanEntry("ex2", "Plank", "timed", target_seconds=30),
    ]


def _circuit() -> list[PlanEntry]:
    return [PlanEntry("ex1", "Push-ups", "repetition", target_reps=20)]


def test_start_sets_warmup_and_first_entry(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    assert engine.state is not None
    assert engine.state.phase == "warmup"
    assert engine.state.status == STATUS_RUNNING
    assert engine.state.current_entry.exercise_name == "Push-ups"
    assert engine.state.current_loop == 0


def test_cannot_start_twice(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    with pytest.raises(SessionError):
        engine.start("s1", "Morning", _warmup(), _circuit())


def test_cannot_start_empty(engine: SessionEngine) -> None:
    with pytest.raises(SessionError):
        engine.start("s1", "Empty", [], [])


def test_timed_exercise_sets_timer(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.complete_exercise()  # finish push-ups, move to plank (timed)
    assert engine.state.current_entry.exercise_type == "timed"
    assert engine.state.timer_ends_at is not None


def test_completion_event_for_reps(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    event = engine.complete_exercise(reps=15)
    assert event.reps == 15
    assert event.seconds is None


def test_completion_defaults_to_target_reps(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    event = engine.complete_exercise()
    assert event.reps == 10


def test_timed_completion_records_elapsed(
    engine: SessionEngine, clock: list[datetime]
) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.complete_exercise()  # push-ups -> plank
    clock[0] = clock[0] + timedelta(seconds=42)
    event = engine.complete_exercise()  # plank
    assert event.seconds == 42


def test_warmup_to_circuit_transition(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.complete_exercise()  # push-ups
    engine.complete_exercise()  # plank -> circuit
    assert engine.state.phase == "circuit"
    assert engine.state.current_loop == 1


def test_circuit_completion_awaits_continue(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.complete_exercise()
    engine.complete_exercise()  # into circuit
    engine.complete_exercise()  # finish single-entry circuit
    assert engine.state.status == STATUS_AWAITING_CONTINUE
    assert engine.state.loop_count == 1


def test_continue_circuit_increments_loop(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.complete_exercise()
    engine.complete_exercise()
    engine.complete_exercise()  # awaiting continue, loop_count=1
    engine.continue_circuit()
    assert engine.state.status == STATUS_RUNNING
    assert engine.state.current_loop == 2
    engine.complete_exercise()
    assert engine.state.loop_count == 2


def test_continue_only_when_awaiting(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    with pytest.raises(SessionError):
        engine.continue_circuit()


def test_pause_resume_preserves_timer(
    engine: SessionEngine, clock: list[datetime]
) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.complete_exercise()  # -> plank timed, 30s timer
    clock[0] = clock[0] + timedelta(seconds=10)
    engine.pause()
    assert engine.state.status == STATUS_PAUSED
    assert engine.state.paused_remaining == pytest.approx(20.0, abs=0.5)
    clock[0] = clock[0] + timedelta(seconds=100)  # time passes while paused
    engine.resume()
    assert engine.state.status == STATUS_RUNNING
    remaining = (
        datetime.fromisoformat(engine.state.timer_ends_at) - clock[0]
    ).total_seconds()
    assert remaining == pytest.approx(20.0, abs=0.5)


def test_pause_requires_running(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.pause()
    with pytest.raises(SessionError):
        engine.pause()
    with pytest.raises(SessionError):
        engine.complete_exercise()


def test_skip_advances_without_event(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.skip_exercise()
    assert engine.state.current_entry.exercise_name == "Plank"


def test_stop_clears_state(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.stop()
    assert engine.state is None


def test_warmup_only_session_completes(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), [])
    engine.complete_exercise()
    engine.complete_exercise()
    assert engine.state is None


def test_state_serialization_round_trip(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    engine.complete_exercise()
    data = engine.state.to_dict()
    restored = SessionState.from_dict(data)
    assert restored.session_name == "Morning"
    assert restored.current_entry.exercise_name == "Plank"
    assert restored.timer_ends_at == engine.state.timer_ends_at


def test_progress_pct(engine: SessionEngine) -> None:
    engine.start("s1", "Morning", _warmup(), _circuit())
    assert engine.state.progress_pct == 0
    engine.complete_exercise()
    assert engine.state.progress_pct == 50
