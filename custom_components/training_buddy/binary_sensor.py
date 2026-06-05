"""Binary sensor platform for Training Buddy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TrainingBuddyConfigEntry
from .coordinator import TrainingBuddyCoordinator
from .entity import ControllerEntity
from .runtime import RuntimeManager


@dataclass(frozen=True, kw_only=True)
class ControllerBinaryDescription(BinarySensorEntityDescription):
    """Describes a controller binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool]


BINARY_SENSORS: tuple[ControllerBinaryDescription, ...] = (
    ControllerBinaryDescription(
        key="workout_active",
        translation_key="workout_active",
        name="Workout Active",
        icon="mdi:run-fast",
        value_fn=lambda s: bool(s.get("active")),
    ),
    ControllerBinaryDescription(
        key="workout_paused",
        translation_key="workout_paused",
        name="Workout Paused",
        icon="mdi:pause-circle",
        value_fn=lambda s: bool(s.get("paused")),
    ),
)


class ControllerBinarySensor(ControllerEntity, BinarySensorEntity):
    """A live session binary sensor on the controller device."""

    entity_description: ControllerBinaryDescription

    def __init__(
        self,
        coordinator: TrainingBuddyCoordinator,
        description: ControllerBinaryDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the binary state from the snapshot."""
        return self.entity_description.value_fn(self.snapshot)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrainingBuddyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Training Buddy binary sensors."""
    runtime: RuntimeManager = entry.runtime_data
    async_add_entities(
        ControllerBinarySensor(runtime.coordinator, desc)
        for desc in BINARY_SENSORS
    )
