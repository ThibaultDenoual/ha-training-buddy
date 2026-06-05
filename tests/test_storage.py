"""Tests for the storage layer."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant

from custom_components.training_buddy.models import Definitions
from custom_components.training_buddy.session_engine import (
    CompletionEvent,
    PlanEntry,
    SessionEngine,
)
from custom_components.training_buddy.statistics import StatisticsEngine
from custom_components.training_buddy.storage import TrainingBuddyStore


async def test_definitions_round_trip(
    hass: HomeAssistant, sample_definitions: Definitions
) -> None:
    store = TrainingBuddyStore(hass)
    await store.async_save_definitions(sample_definitions)
    loaded = await store.async_load_definitions()
    assert len(loaded.exercises) == len(sample_definitions.exercises)
    assert len(loaded.sessions) == len(sample_definitions.sessions)


async def test_empty_definitions(hass: HomeAssistant) -> None:
    store = TrainingBuddyStore(hass)
    loaded = await store.async_load_definitions()
    assert loaded.exercises == {}


async def test_statistics_round_trip(hass: HomeAssistant) -> None:
    store = TrainingBuddyStore(hass)
    engine = StatisticsEngine()
    engine.apply(
        CompletionEvent(
            exercise_id="ex1",
            exercise_type="repetition",
            reps=20,
            seconds=None,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        )
    )
    await store.async_save_statistics(engine)
    loaded = await store.async_load_statistics()
    assert loaded.get("ex1").total_reps == 20


async def test_runtime_round_trip(
    hass: HomeAssistant, fixed_now: datetime
) -> None:
    store = TrainingBuddyStore(hass)
    engine = SessionEngine(now=lambda: fixed_now)
    engine.start(
        "s1",
        "Morning",
        [PlanEntry("ex1", "Push-ups", "repetition", target_reps=10)],
        [],
    )
    await store.async_save_runtime(engine.state)
    loaded = await store.async_load_runtime()
    assert loaded is not None
    assert loaded.session_name == "Morning"

    await store.async_save_runtime(None)
    assert await store.async_load_runtime() is None
