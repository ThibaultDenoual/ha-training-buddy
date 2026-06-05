"""Coordinator for Training Buddy.

This integration has **no external data to poll** — all state is local and
changes are driven by user actions. We still use a ``DataUpdateCoordinator``,
but purely as a push-based state-distribution hub: ``update_interval`` is
``None`` and updates are delivered with :meth:`async_set_updated_data` from the
runtime manager. Entities subscribe through ``CoordinatorEntity`` and get free
listener bookkeeping. This is a deliberate, idiomatic use of the coordinator
for a local-push integration (see ARCHITECTURE.md).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

if TYPE_CHECKING:
    from .runtime import RuntimeManager

_LOGGER = logging.getLogger(__name__)


class TrainingBuddyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Push-based coordinator acting as the entity state hub."""

    runtime: RuntimeManager

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator with polling disabled."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=None,  # local push only — never polls
            config_entry=entry,
        )

    def attach_runtime(self, runtime: RuntimeManager) -> None:
        """Wire the runtime manager so entities can reach engines."""
        self.runtime = runtime

    async def _async_update_data(self) -> dict[str, Any]:
        """Return the current snapshot.

        Called once on first refresh; thereafter the runtime manager pushes
        updates via :meth:`async_set_updated_data`.
        """
        return self.runtime.build_snapshot()
