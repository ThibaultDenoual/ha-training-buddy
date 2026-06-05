"""Tests for the pure statistics engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.training_buddy.session_engine import CompletionEvent
from custom_components.training_buddy.statistics import (
    ExerciseStats,
    StatisticsEngine,
)


def _rep_event(ts: datetime, reps: int) -> CompletionEvent:
    return CompletionEvent(
        exercise_id="ex1",
        exercise_type="repetition",
        reps=reps,
        seconds=None,
        timestamp=ts.isoformat(),
    )


def _timed_event(ts: datetime, seconds: int) -> CompletionEvent:
    return CompletionEvent(
        exercise_id="ex2",
        exercise_type="timed",
        reps=None,
        seconds=seconds,
        timestamp=ts.isoformat(),
    )


def test_repetition_aggregates() -> None:
    engine = StatisticsEngine()
    now = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    engine.apply(_rep_event(now, 10))
    engine.apply(_rep_event(now, 25))
    stats = engine.get("ex1")
    assert stats.times_completed == 2
    assert stats.total_reps == 35
    assert stats.personal_best_reps == 25
    assert stats.last_completed == now.isoformat()


def test_timed_aggregates() -> None:
    engine = StatisticsEngine()
    now = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    engine.apply(_timed_event(now, 30))
    engine.apply(_timed_event(now, 65))
    stats = engine.get("ex2")
    assert stats.times_completed == 2
    assert stats.total_seconds == 95
    assert stats.longest_seconds == 65


def test_streak_consecutive_days() -> None:
    stats = ExerciseStats(exercise_id="ex1")
    base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    for day in range(5):
        stats.apply(_rep_event(base + timedelta(days=day), 10))
    assert stats.current_streak == 5
    assert stats.longest_streak == 5


def test_streak_resets_on_gap() -> None:
    stats = ExerciseStats(exercise_id="ex1")
    base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    stats.apply(_rep_event(base, 10))
    stats.apply(_rep_event(base + timedelta(days=1), 10))
    stats.apply(_rep_event(base + timedelta(days=5), 10))  # gap
    assert stats.current_streak == 1
    assert stats.longest_streak == 2


def test_same_day_does_not_increase_streak() -> None:
    stats = ExerciseStats(exercise_id="ex1")
    base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    stats.apply(_rep_event(base, 10))
    stats.apply(_rep_event(base + timedelta(hours=2), 10))
    assert stats.current_streak == 1


def test_windowed_reps() -> None:
    stats = ExerciseStats(exercise_id="ex1")
    now = datetime(2026, 1, 31, 8, 0, tzinfo=UTC)
    stats.apply(_rep_event(now - timedelta(days=2), 10))  # within week
    stats.apply(_rep_event(now - timedelta(days=10), 20))  # within month
    stats.apply(_rep_event(now - timedelta(days=39), 30))  # within retention
    assert stats.reps_in_last_days(7, now) == 10
    assert stats.reps_in_last_days(30, now) == 30


def test_history_pruned_to_retention() -> None:
    stats = ExerciseStats(exercise_id="ex1")
    old = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    stats.apply(_rep_event(old, 10))
    # A completion 100 days later should prune the old record.
    stats.apply(_rep_event(old + timedelta(days=100), 5))
    assert len(stats.history) == 1
    # But lifetime aggregates remain intact.
    assert stats.total_reps == 15


def test_round_trip() -> None:
    engine = StatisticsEngine()
    now = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    engine.apply(_rep_event(now, 10))
    restored = StatisticsEngine()
    restored.load(engine.to_dict())
    assert restored.get("ex1").total_reps == 10


def test_remove() -> None:
    engine = StatisticsEngine()
    engine.apply(_rep_event(datetime(2026, 1, 1, tzinfo=UTC), 10))
    engine.remove("ex1")
    assert "ex1" not in engine.all_stats
