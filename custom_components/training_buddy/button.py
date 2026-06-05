"""Button platform for Training Buddy.

Buttons provide one-tap session control on the controller device. Because a
button carries no parameters, the **Start Session** button starts the first
defined session; selecting a specific session is done with the
``training_buddy.start_session`` service (see roadmap: per-session start /
select entity).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TrainingBuddyConfigEntry
from .coordinator import TrainingBuddyCoordinator
from .entity import ControllerEntity
from .runtime import RuntimeManager
from .session_engine import SessionError


async def _start_first_session(runtime: RuntimeManager) -> None:
    sessions = list(runtime.definitions.sessions.values())
    if not sessions:
        raise HomeAssistantError("No session defined to start")
    await runtime.async_start_session(sessions[0].id)


@dataclass(frozen=True, kw_only=True)
class ControllerButtonDescription(ButtonEntityDescription):
    """Describes a controller button."""

    press_fn: Callable[[RuntimeManager], Awaitable[None]]


BUTTONS: tuple[ControllerButtonDescription, ...] = (
    ControllerButtonDescription(
        key="start_session",
        translation_key="start_session",
        name="Start Session",
        icon="mdi:play",
        press_fn=_start_first_session,
    ),
    ControllerButtonDescription(
        key="pause_session",
        translation_key="pause_session",
        name="Pause Session",
        icon="mdi:pause",
        press_fn=lambda r: r.async_pause_session(),
    ),
    ControllerButtonDescription(
        key="resume_session",
        translation_key="resume_session",
        name="Resume Session",
        icon="mdi:play-pause",
        press_fn=lambda r: r.async_resume_session(),
    ),
    ControllerButtonDescription(
        key="stop_session",
        translation_key="stop_session",
        name="Stop Session",
        icon="mdi:stop",
        press_fn=lambda r: r.async_stop_session(),
    ),
    ControllerButtonDescription(
        key="complete_exercise",
        translation_key="complete_exercise",
        name="Complete Exercise",
        icon="mdi:check",
        press_fn=lambda r: r.async_complete_exercise(),
    ),
    ControllerButtonDescription(
        key="skip_exercise",
        translation_key="skip_exercise",
        name="Skip Exercise",
        icon="mdi:skip-next",
        press_fn=lambda r: r.async_skip_exercise(),
    ),
    ControllerButtonDescription(
        key="continue_circuit",
        translation_key="continue_circuit",
        name="Continue Circuit",
        icon="mdi:rotate-right",
        press_fn=lambda r: r.async_continue_circuit(),
    ),
)


class ControllerButton(ControllerEntity, ButtonEntity):
    """A session-control button on the controller device."""

    entity_description: ControllerButtonDescription

    def __init__(
        self,
        coordinator: TrainingBuddyCoordinator,
        description: ControllerButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.entity_description.press_fn(self.coordinator.runtime)
        except SessionError as err:
            raise ServiceValidationError(str(err)) from err


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrainingBuddyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Training Buddy buttons."""
    runtime: RuntimeManager = entry.runtime_data
    async_add_entities(
        ControllerButton(runtime.coordinator, desc) for desc in BUTTONS
    )
