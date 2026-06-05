"""Domain models for Training Buddy.

This module is intentionally free of any Home Assistant imports. It defines the
pure domain model (exercises, rounds, sessions) plus serialization helpers so
it can be unit tested in isolation and reused outside of Home Assistant.

Design notes
------------
* Definitions are normalized. A :class:`RoundEntry` references an
  :class:`Exercise` by ``exercise_id`` and supplies *round-specific* targets.
  The same exercise can therefore appear in many rounds with different targets
  without ever being duplicated.
* New exercise types can be added by extending the validation helpers without
  touching the storage schema (the ``type`` field is an open string validated
  against a known set).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .const import (
    ALL_EXERCISE_TYPES,
    DURATION_EXERCISE_TYPES,
    EXERCISE_TYPE_REPETITION,
    REPETITION_EXERCISE_TYPES,
)


class ValidationError(ValueError):
    """Raised when a domain object fails validation."""


def new_id() -> str:
    """Return a new opaque, stable identifier."""
    return uuid.uuid4().hex


@dataclass(slots=True)
class Exercise:
    """A reusable exercise definition.

    An exercise carries *no* target (reps/duration). Targets are supplied per
    round entry, allowing reuse across rounds and sessions.
    """

    name: str
    type: str
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Normalize and validate the exercise."""
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError("Exercise name must not be empty")
        if self.type not in ALL_EXERCISE_TYPES:
            raise ValidationError(f"Unknown exercise type: {self.type!r}")

    @property
    def is_duration_based(self) -> bool:
        """Return True if this exercise's target is a duration in seconds."""
        return self.type in DURATION_EXERCISE_TYPES

    @property
    def is_repetition_based(self) -> bool:
        """Return True if this exercise's target is a repetition count."""
        return self.type in REPETITION_EXERCISE_TYPES

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {"id": self.id, "name": self.name, "type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Exercise:
        """Deserialize from storage."""
        return cls(id=data["id"], name=data["name"], type=data["type"])


@dataclass(slots=True)
class RoundEntry:
    """An ordered reference to an exercise with round-specific targets.

    Exactly one of ``target_reps`` / ``target_seconds`` is meaningful depending
    on the referenced exercise type. The other is ``None``.
    """

    exercise_id: str
    target_reps: int | None = None
    target_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "exercise_id": self.exercise_id,
            "target_reps": self.target_reps,
            "target_seconds": self.target_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoundEntry:
        """Deserialize from storage."""
        return cls(
            exercise_id=data["exercise_id"],
            target_reps=data.get("target_reps"),
            target_seconds=data.get("target_seconds"),
        )


@dataclass(slots=True)
class Round:
    """An ordered collection of round entries."""

    name: str
    entries: list[RoundEntry] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Normalize and validate the round."""
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError("Round name must not be empty")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Round:
        """Deserialize from storage."""
        return cls(
            id=data["id"],
            name=data["name"],
            entries=[RoundEntry.from_dict(e) for e in data.get("entries", [])],
        )


@dataclass(slots=True)
class Session:
    """A workout template made of a warm-up round and a circuit round."""

    name: str
    warmup_round_id: str | None = None
    circuit_round_id: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Normalize and validate the session."""
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError("Session name must not be empty")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "warmup_round_id": self.warmup_round_id,
            "circuit_round_id": self.circuit_round_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Deserialize from storage."""
        return cls(
            id=data["id"],
            name=data["name"],
            warmup_round_id=data.get("warmup_round_id"),
            circuit_round_id=data.get("circuit_round_id"),
        )


@dataclass(slots=True)
class Definitions:
    """The full set of user-defined exercises, rounds and sessions."""

    exercises: dict[str, Exercise] = field(default_factory=dict)
    rounds: dict[str, Round] = field(default_factory=dict)
    sessions: dict[str, Session] = field(default_factory=dict)

    # -- exercises ------------------------------------------------------------
    def add_exercise(self, exercise: Exercise) -> Exercise:
        """Add an exercise definition."""
        self.exercises[exercise.id] = exercise
        return exercise

    def remove_exercise(self, exercise_id: str) -> None:
        """Remove an exercise and any round entries that reference it."""
        self.exercises.pop(exercise_id, None)
        for rnd in self.rounds.values():
            rnd.entries = [
                e for e in rnd.entries if e.exercise_id != exercise_id
            ]

    # -- rounds ---------------------------------------------------------------
    def add_round(self, rnd: Round) -> Round:
        """Add a round definition."""
        self.rounds[rnd.id] = rnd
        return rnd

    def remove_round(self, round_id: str) -> None:
        """Remove a round and detach it from any session referencing it."""
        self.rounds.pop(round_id, None)
        for session in self.sessions.values():
            if session.warmup_round_id == round_id:
                session.warmup_round_id = None
            if session.circuit_round_id == round_id:
                session.circuit_round_id = None

    # -- sessions -------------------------------------------------------------
    def add_session(self, session: Session) -> Session:
        """Add a session definition."""
        self.sessions[session.id] = session
        return session

    def remove_session(self, session_id: str) -> None:
        """Remove a session definition."""
        self.sessions.pop(session_id, None)

    # -- integrity ------------------------------------------------------------
    def validate_round_entries(self, rnd: Round) -> None:
        """Validate a round's entries against known exercises and targets.

        Each entry must reference a known exercise and carry the correct
        target for that exercise type.
        """
        for entry in rnd.entries:
            exercise = self.exercises.get(entry.exercise_id)
            if exercise is None:
                raise ValidationError(
                    f"Round {rnd.name!r} references unknown exercise "
                    f"{entry.exercise_id!r}"
                )
            if exercise.is_repetition_based and entry.target_reps is None:
                raise ValidationError(
                    f"Entry for {exercise.name!r} requires target_reps"
                )
            if exercise.is_duration_based and entry.target_seconds is None:
                raise ValidationError(
                    f"Entry for {exercise.name!r} requires target_seconds"
                )

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "exercises": {k: v.to_dict() for k, v in self.exercises.items()},
            "rounds": {k: v.to_dict() for k, v in self.rounds.items()},
            "sessions": {k: v.to_dict() for k, v in self.sessions.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Definitions:
        """Deserialize from storage, tolerating an empty store."""
        if not data:
            return cls()
        return cls(
            exercises={
                k: Exercise.from_dict(v)
                for k, v in data.get("exercises", {}).items()
            },
            rounds={
                k: Round.from_dict(v)
                for k, v in data.get("rounds", {}).items()
            },
            sessions={
                k: Session.from_dict(v)
                for k, v in data.get("sessions", {}).items()
            },
        )


# Default repetition target used when a repetition exercise is created without
# an explicit per-round target. Kept here so engine and UI agree.
DEFAULT_TARGET_REPS = 10
DEFAULT_TARGET_SECONDS = 30

# Re-export to keep callers importing from one place.
__all__ = [
    "DEFAULT_TARGET_REPS",
    "DEFAULT_TARGET_SECONDS",
    "EXERCISE_TYPE_REPETITION",
    "Definitions",
    "Exercise",
    "Round",
    "RoundEntry",
    "Session",
    "ValidationError",
    "new_id",
]
