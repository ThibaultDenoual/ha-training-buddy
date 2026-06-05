"""The Training Buddy integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import TrainingBuddyCoordinator
from .runtime import RuntimeManager
from .services import async_setup_services, async_unload_services
from .storage import TrainingBuddyStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
]

# The runtime manager is stored on the config entry's runtime_data (the modern
# pattern that replaces hass.data[DOMAIN]).
type TrainingBuddyConfigEntry = ConfigEntry[RuntimeManager]


async def async_setup_entry(
    hass: HomeAssistant, entry: TrainingBuddyConfigEntry
) -> bool:
    """Set up Training Buddy from a config entry."""
    store = TrainingBuddyStore(hass)
    coordinator = TrainingBuddyCoordinator(hass, entry)
    runtime = RuntimeManager(hass, store, coordinator)
    coordinator.attach_runtime(runtime)

    await runtime.async_setup()
    entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: TrainingBuddyConfigEntry
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unloaded:
        await entry.runtime_data.async_unload()
        async_unload_services(hass)
    return unloaded


async def async_remove_entry(
    hass: HomeAssistant, entry: TrainingBuddyConfigEntry
) -> None:
    """Remove all persisted data when the integration is deleted."""
    store = TrainingBuddyStore(hass)
    await store.async_remove_all()


async def _async_update_listener(
    hass: HomeAssistant, entry: TrainingBuddyConfigEntry
) -> None:
    """Reload entities when definitions change via the options flow."""
    # Structural changes are pushed live through dispatcher signals; a full
    # reload keeps device/entity registries consistent after bulk edits.
    await hass.config_entries.async_reload(entry.entry_id)
