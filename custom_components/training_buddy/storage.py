"""Persistence layer for Training Buddy.

All durable state lives here, never in YAML and never in the config entry.
Three separate :class:`homeassistant.helpers.storage.Store` instances are used
to isolate write-frequency concerns:

* ``definitions`` — exercises/rounds/sessions. Written rarely (on edits).
* ``statistics`` — per-exercise aggregates. Written once per completion.
* ``runtime`` — the active session. Written on every workout action, so keeping
  it separate avoids rewriting the (potentially large) definitions blob on
  every timer tick.

Each store carries its own version and migration function so schemas can evolve
independently.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    STORAGE_KEY_DEFINITIONS,
    STORAGE_KEY_RUNTIME,
    STORAGE_KEY_STATISTICS,
    STORAGE_VERSION_DEFINITIONS,
    STORAGE_VERSION_RUNTIME,
    STORAGE_VERSION_STATISTICS,
)
from .models import Definitions
from .session_engine import SessionState
from .statistics import StatisticsEngine

_LOGGER = logging.getLogger(__name__)


class _DefinitionsStore(Store[dict[str, Any]]):
    """Definitions store with a migration hook for future schema changes."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        # No migrations yet; future versions branch on old_major_version.
        _LOGGER.debug(
            "Migrating definitions store from version %s.%s",
            old_major_version,
            old_minor_version,
        )
        return old_data


class TrainingBuddyStore:
    """Aggregate facade over the three underlying stores."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the store facade."""
        self._definitions_store = _DefinitionsStore(
            hass, STORAGE_VERSION_DEFINITIONS, STORAGE_KEY_DEFINITIONS
        )
        self._statistics_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION_STATISTICS, STORAGE_KEY_STATISTICS
        )
        self._runtime_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION_RUNTIME, STORAGE_KEY_RUNTIME
        )

    # -- definitions ----------------------------------------------------------
    async def async_load_definitions(self) -> Definitions:
        """Load definitions, returning an empty set if none stored."""
        data = await self._definitions_store.async_load()
        return Definitions.from_dict(data)

    async def async_save_definitions(self, definitions: Definitions) -> None:
        """Persist definitions."""
        await self._definitions_store.async_save(definitions.to_dict())

    # -- statistics -----------------------------------------------------------
    async def async_load_statistics(self) -> StatisticsEngine:
        """Load statistics into a fresh engine."""
        data = await self._statistics_store.async_load()
        engine = StatisticsEngine()
        engine.load(data)
        return engine

    async def async_save_statistics(self, engine: StatisticsEngine) -> None:
        """Persist statistics."""
        await self._statistics_store.async_save(engine.to_dict())

    # -- runtime --------------------------------------------------------------
    async def async_load_runtime(self) -> SessionState | None:
        """Load the active session state, if any."""
        data = await self._runtime_store.async_load()
        if not data or not data.get("session"):
            return None
        return SessionState.from_dict(data["session"])

    async def async_save_runtime(self, state: SessionState | None) -> None:
        """Persist (or clear) the active session state."""
        payload = {"session": state.to_dict() if state is not None else None}
        await self._runtime_store.async_save(payload)

    async def async_remove_all(self) -> None:
        """Remove all stored data (used when the integration is removed)."""
        await self._definitions_store.async_remove()
        await self._statistics_store.async_remove()
        await self._runtime_store.async_remove()
