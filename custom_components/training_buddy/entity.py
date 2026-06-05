"""Shared entity base classes and device helpers for Training Buddy.

Two kinds of devices exist:

* a single **controller** device that hosts the runtime entities (current
  exercise, progress, buttons, ...), and
* one **device per exercise** that hosts that exercise's statistics sensors.

Exercise devices are linked to the controller via ``via_device`` so the UI
groups them sensibly.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONTROLLER_DEVICE_ID, DOMAIN, MANUFACTURER
from .coordinator import TrainingBuddyCoordinator
from .models import Exercise


def controller_device_info() -> DeviceInfo:
    """Return the device info for the controller device."""
    return DeviceInfo(
        identifiers={(DOMAIN, CONTROLLER_DEVICE_ID)},
        name="Training Buddy",
        manufacturer=MANUFACTURER,
        model="Workout Controller",
        entry_type=None,
    )


def exercise_device_info(exercise: Exercise) -> DeviceInfo:
    """Return the device info for an exercise device."""
    return DeviceInfo(
        identifiers={(DOMAIN, exercise.id)},
        name=exercise.name,
        manufacturer=MANUFACTURER,
        model=f"Exercise ({exercise.type})",
        via_device=(DOMAIN, CONTROLLER_DEVICE_ID),
    )


class ControllerEntity(CoordinatorEntity[TrainingBuddyCoordinator]):
    """Base for entities attached to the controller device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: TrainingBuddyCoordinator, key: str
    ) -> None:
        """Initialize a controller entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_device_info = controller_device_info()

    @property
    def snapshot(self) -> dict:
        """Return the current coordinator snapshot."""
        return self.coordinator.data or {}


class ExerciseEntity(CoordinatorEntity[TrainingBuddyCoordinator]):
    """Base for entities attached to an exercise device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TrainingBuddyCoordinator,
        exercise: Exercise,
        key: str,
    ) -> None:
        """Initialize an exercise entity."""
        super().__init__(coordinator)
        self._exercise = exercise
        self._attr_unique_id = f"{DOMAIN}_{exercise.id}_{key}"
        self._attr_device_info = exercise_device_info(exercise)
