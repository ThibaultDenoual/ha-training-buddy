"""Tests for the pure domain models."""

from __future__ import annotations

import pytest

from custom_components.training_buddy.models import (
    Definitions,
    Exercise,
    Round,
    RoundEntry,
    Session,
    ValidationError,
)


def test_exercise_validation() -> None:
    with pytest.raises(ValidationError):
        Exercise(name="  ", type="repetition")
    with pytest.raises(ValidationError):
        Exercise(name="Push-ups", type="nonsense")


def test_exercise_type_properties() -> None:
    assert Exercise(name="Push-ups", type="repetition").is_repetition_based
    assert Exercise(name="Plank", type="timed").is_duration_based
    assert Exercise(name="Rest", type="rest").is_duration_based


def test_exercise_reuse_without_duplication() -> None:
    defs = Definitions()
    pushups = defs.add_exercise(Exercise(name="Push-ups", type="repetition"))
    warmup = defs.add_round(
        Round(name="Warm-up", entries=[RoundEntry(pushups.id, target_reps=10)])
    )
    circuit = defs.add_round(
        Round(name="Circuit", entries=[RoundEntry(pushups.id, target_reps=20)])
    )
    # Same exercise referenced by two rounds, one definition only.
    assert len(defs.exercises) == 1
    assert warmup.entries[0].exercise_id == circuit.entries[0].exercise_id


def test_remove_exercise_cascades_to_round_entries() -> None:
    defs = Definitions()
    pushups = defs.add_exercise(Exercise(name="Push-ups", type="repetition"))
    rnd = defs.add_round(
        Round(name="R", entries=[RoundEntry(pushups.id, target_reps=10)])
    )
    defs.remove_exercise(pushups.id)
    assert rnd.entries == []


def test_remove_round_detaches_from_session() -> None:
    defs = Definitions()
    rnd = defs.add_round(Round(name="Warm-up"))
    session = defs.add_session(
        Session(name="S", warmup_round_id=rnd.id, circuit_round_id=rnd.id)
    )
    defs.remove_round(rnd.id)
    assert session.warmup_round_id is None
    assert session.circuit_round_id is None


def test_validate_round_entries_requires_targets() -> None:
    defs = Definitions()
    pushups = defs.add_exercise(Exercise(name="Push-ups", type="repetition"))
    plank = defs.add_exercise(Exercise(name="Plank", type="timed"))
    bad_reps = Round(name="bad", entries=[RoundEntry(pushups.id)])
    with pytest.raises(ValidationError):
        defs.validate_round_entries(bad_reps)
    bad_secs = Round(name="bad", entries=[RoundEntry(plank.id)])
    with pytest.raises(ValidationError):
        defs.validate_round_entries(bad_secs)
    unknown = Round(name="bad", entries=[RoundEntry("missing", target_reps=1)])
    with pytest.raises(ValidationError):
        defs.validate_round_entries(unknown)


def test_definitions_round_trip(sample_definitions: Definitions) -> None:
    restored = Definitions.from_dict(sample_definitions.to_dict())
    assert len(restored.exercises) == len(sample_definitions.exercises)
    assert len(restored.rounds) == len(sample_definitions.rounds)
    assert len(restored.sessions) == len(sample_definitions.sessions)


def test_definitions_from_empty() -> None:
    assert Definitions.from_dict(None).exercises == {}
    assert Definitions.from_dict({}).rounds == {}
