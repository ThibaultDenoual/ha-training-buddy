"""Integration tests for setup, entities, services and persistence."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.training_buddy.const import DOMAIN
from custom_components.training_buddy.models import Definitions, Exercise


async def _setup(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _loop_count(hass: HomeAssistant) -> str:
    return hass.states.get("sensor.training_buddy_circuit_loop_count").state


def _active(hass: HomeAssistant) -> str:
    return hass.states.get("binary_sensor.training_buddy_workout_active").state


def _current(hass: HomeAssistant) -> str:
    return hass.states.get("sensor.training_buddy_current_exercise").state


async def test_setup_creates_controller_entities(
    hass: HomeAssistant, mock_config_entry
) -> None:
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.training_buddy_current_exercise")
    assert hass.states.get("sensor.training_buddy_session_progress")
    assert hass.states.get("sensor.training_buddy_circuit_loop_count")
    assert _active(hass) == "off"
    assert hass.states.get("button.training_buddy_start_session")


async def test_services_registered(
    hass: HomeAssistant, mock_config_entry
) -> None:
    await _setup(hass, mock_config_entry)
    for service in (
        "start_session",
        "pause_session",
        "resume_session",
        "stop_session",
        "complete_exercise",
        "skip_exercise",
        "continue_circuit",
    ):
        assert hass.services.has_service(DOMAIN, service)


async def test_full_session_via_services(
    hass: HomeAssistant, mock_config_entry, sample_definitions: Definitions
) -> None:
    await _setup(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data
    runtime.definitions = sample_definitions
    session_id = next(iter(sample_definitions.sessions))

    async def call(service: str, **data) -> None:
        await hass.services.async_call(DOMAIN, service, data, blocking=True)

    # Warm-up: Push-ups, then Plank.
    await call("start_session", session_id=session_id)
    assert _current(hass) == "Push-ups"
    assert _active(hass) == "on"

    await call("complete_exercise", reps=12)
    assert _current(hass) == "Plank"

    await call("pause_session")
    assert (
        hass.states.get("binary_sensor.training_buddy_workout_paused").state
        == "on"
    )
    await call("resume_session")

    # Completing the Plank ends the warm-up and starts the circuit (loop 0).
    await call("complete_exercise")
    assert _current(hass) == "Push-ups"
    assert _loop_count(hass) == "0"

    # Completing the circuit's only exercise finishes a loop and awaits.
    await call("complete_exercise")
    assert _loop_count(hass) == "1"

    await call("continue_circuit")
    assert _loop_count(hass) == "1"  # completed loops unchanged until finished

    await call("stop_session")
    assert _active(hass) == "off"


async def test_session_survives_reload(
    hass: HomeAssistant, mock_config_entry, sample_definitions: Definitions
) -> None:
    await _setup(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data
    runtime.definitions = sample_definitions
    session_id = next(iter(sample_definitions.sessions))

    await runtime.async_start_session(session_id)
    await runtime.async_complete_exercise()  # now on Plank

    # Simulate a restart: unload then set up again.
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # The active session is restored even though definitions were not
    # persisted, because the plan is snapshotted into runtime state.
    assert _current(hass) == "Plank"


async def test_exercise_device_and_stats_sensors(
    hass: HomeAssistant, mock_config_entry
) -> None:
    await _setup(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data

    # Add an exercise through the runtime (fires the dispatcher signal).
    await runtime.async_add_exercise(
        Exercise(name="Squats", type="repetition", id="squats")
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.squats_total_reps")
    assert state is not None
    assert state.state == "0"
