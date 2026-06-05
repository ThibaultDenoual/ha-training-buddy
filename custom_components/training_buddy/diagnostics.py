"""Diagnostics support for Training Buddy."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import TrainingBuddyConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TrainingBuddyConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    No personal data is stored by this integration, so nothing is redacted.
    """
    runtime = entry.runtime_data
    state = runtime.engine.state
    return {
        "definitions": {
            "exercises": len(runtime.definitions.exercises),
            "rounds": len(runtime.definitions.rounds),
            "sessions": len(runtime.definitions.sessions),
        },
        "active_session": state.to_dict() if state is not None else None,
        "snapshot": runtime.build_snapshot(),
        "statistics": runtime.stats.to_dict(),
    }
