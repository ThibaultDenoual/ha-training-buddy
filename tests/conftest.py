"""Pytest configuration and shared fixtures for Training Buddy tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest

from custom_components.training_buddy.const import DOMAIN
from custom_components.training_buddy.models import (
    Definitions,
    Exercise,
    Round,
    RoundEntry,
    Session,
)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading of the custom integration in every test."""
    yield


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry for Training Buddy."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        title="Training Buddy",
        data={},
        unique_id=DOMAIN,
    )


@pytest.fixture
def sample_definitions() -> Definitions:
    """Return a small set of definitions for tests."""
    defs = Definitions()
    pushups = defs.add_exercise(Exercise(name="Push-ups", type="repetition"))
    plank = defs.add_exercise(Exercise(name="Plank", type="timed"))
    warmup = defs.add_round(
        Round(
            name="Warm-up",
            entries=[
                RoundEntry(pushups.id, target_reps=10),
                RoundEntry(plank.id, target_seconds=30),
            ],
        )
    )
    circuit = defs.add_round(
        Round(
            name="Circuit",
            entries=[RoundEntry(pushups.id, target_reps=20)],
        )
    )
    defs.add_session(
        Session(
            name="Morning Workout",
            warmup_round_id=warmup.id,
            circuit_round_id=circuit.id,
        )
    )
    return defs


@pytest.fixture
def fixed_now() -> datetime:
    """Return a fixed UTC timestamp for deterministic tests."""
    return datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
