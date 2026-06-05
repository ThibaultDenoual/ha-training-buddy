"""The Training Buddy statistics engine.

Pure, Home-Assistant-free aggregation of :class:`CompletionEvent` objects into
per-exercise statistics. Lifetime aggregates and streaks are updated
incrementally so we never need to keep an unbounded completion log; only a
short rolling window is retained to compute weekly / monthly totals.

Extensibility
-------------
New statistics generally fall into two buckets:

* *Incremental aggregates* (counters, maxima, streaks) — add a field to
  :class:`ExerciseStats` and update it in :meth:`ExerciseStats.apply`.
* *Windowed metrics* — add a helper that sums over
  :attr:`ExerciseStats.history`, like :meth:`ExerciseStats.reps_in_last_days`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .session_engine import CompletionEvent

# Rolling window retained for weekly/monthly derived metrics. A little headroom
# over a month keeps month boundaries correct without unbounded growth.
_HISTORY_RETENTION_DAYS = 40


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


@dataclass(slots=True)
class CompletionRecord:
    """A single completion kept in the rolling window."""

    timestamp: str
    reps: int | None
    seconds: int | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "timestamp": self.timestamp,
            "reps": self.reps,
            "seconds": self.seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompletionRecord:
        """Deserialize from storage."""
        return cls(
            timestamp=data["timestamp"],
            reps=data.get("reps"),
            seconds=data.get("seconds"),
        )


@dataclass(slots=True)
class ExerciseStats:
    """Aggregated statistics for a single exercise."""

    exercise_id: str
    times_completed: int = 0
    total_reps: int = 0
    total_seconds: int = 0
    last_completed: str | None = None
    last_completed_date: str | None = None
    personal_best_reps: int = 0
    longest_seconds: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    history: list[CompletionRecord] = field(default_factory=list)

    def apply(self, event: CompletionEvent) -> None:
        """Fold a completion event into the aggregates."""
        self.times_completed += 1
        self.last_completed = event.timestamp

        if event.reps is not None:
            self.total_reps += event.reps
            self.personal_best_reps = max(self.personal_best_reps, event.reps)
        if event.seconds is not None:
            self.total_seconds += event.seconds
            self.longest_seconds = max(self.longest_seconds, event.seconds)

        self._update_streak(event.timestamp)

        self.history.append(
            CompletionRecord(
                timestamp=event.timestamp,
                reps=event.reps,
                seconds=event.seconds,
            )
        )
        self._prune(_parse(event.timestamp))

    def _update_streak(self, timestamp: str) -> None:
        day = _parse(timestamp).date()
        if self.last_completed_date is None:
            self.current_streak = 1
        else:
            previous = datetime.fromisoformat(self.last_completed_date).date()
            delta = (day - previous).days
            if delta == 0:
                pass  # another completion the same day, streak unchanged
            elif delta == 1:
                self.current_streak += 1
            else:
                self.current_streak = 1
        self.longest_streak = max(self.longest_streak, self.current_streak)
        self.last_completed_date = day.isoformat()

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=_HISTORY_RETENTION_DAYS)
        self.history = [
            r for r in self.history if _parse(r.timestamp) >= cutoff
        ]

    # -- windowed derived metrics --------------------------------------------
    def reps_in_last_days(self, days: int, now: datetime | None = None) -> int:
        """Sum repetitions completed within the last ``days`` days."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        return sum(
            r.reps or 0 for r in self.history if _parse(r.timestamp) >= cutoff
        )

    def seconds_in_last_days(
        self, days: int, now: datetime | None = None
    ) -> int:
        """Sum duration completed within the last ``days`` days."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        return sum(
            r.seconds or 0
            for r in self.history
            if _parse(r.timestamp) >= cutoff
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "exercise_id": self.exercise_id,
            "times_completed": self.times_completed,
            "total_reps": self.total_reps,
            "total_seconds": self.total_seconds,
            "last_completed": self.last_completed,
            "last_completed_date": self.last_completed_date,
            "personal_best_reps": self.personal_best_reps,
            "longest_seconds": self.longest_seconds,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "history": [r.to_dict() for r in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExerciseStats:
        """Deserialize from storage."""
        return cls(
            exercise_id=data["exercise_id"],
            times_completed=data.get("times_completed", 0),
            total_reps=data.get("total_reps", 0),
            total_seconds=data.get("total_seconds", 0),
            last_completed=data.get("last_completed"),
            last_completed_date=data.get("last_completed_date"),
            personal_best_reps=data.get("personal_best_reps", 0),
            longest_seconds=data.get("longest_seconds", 0),
            current_streak=data.get("current_streak", 0),
            longest_streak=data.get("longest_streak", 0),
            history=[
                CompletionRecord.from_dict(r) for r in data.get("history", [])
            ],
        )


class StatisticsEngine:
    """Owns per-exercise statistics and applies completion events."""

    def __init__(self) -> None:
        """Initialize an empty statistics engine."""
        self._stats: dict[str, ExerciseStats] = {}

    @property
    def all_stats(self) -> dict[str, ExerciseStats]:
        """Return the mapping of exercise id to stats."""
        return self._stats

    def get(self, exercise_id: str) -> ExerciseStats:
        """Return (creating if needed) the stats for an exercise."""
        stats = self._stats.get(exercise_id)
        if stats is None:
            stats = ExerciseStats(exercise_id=exercise_id)
            self._stats[exercise_id] = stats
        return stats

    def apply(self, event: CompletionEvent) -> ExerciseStats:
        """Apply a completion event and return the updated stats."""
        stats = self.get(event.exercise_id)
        stats.apply(event)
        return stats

    def remove(self, exercise_id: str) -> None:
        """Drop statistics for a removed exercise."""
        self._stats.pop(exercise_id, None)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {"stats": {k: v.to_dict() for k, v in self._stats.items()}}

    def load(self, data: dict[str, Any] | None) -> None:
        """Load statistics from storage, tolerating an empty store."""
        self._stats = {}
        if not data:
            return
        for key, value in data.get("stats", {}).items():
            self._stats[key] = ExerciseStats.from_dict(value)
