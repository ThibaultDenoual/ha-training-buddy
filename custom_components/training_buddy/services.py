"""Service registration for Training Buddy.

Services are registered at the domain level (not per entity) and delegate
to the single runtime manager. They are fully automation-callable.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_REPS,
    ATTR_SESSION_ID,
    DOMAIN,
    SERVICE_COMPLETE_EXERCISE,
    SERVICE_CONTINUE_CIRCUIT,
    SERVICE_PAUSE_SESSION,
    SERVICE_RESUME_SESSION,
    SERVICE_SKIP_EXERCISE,
    SERVICE_START_SESSION,
    SERVICE_STOP_SESSION,
)
from .runtime import RuntimeManager
from .session_engine import SessionError

_START_SCHEMA = vol.Schema({vol.Required(ATTR_SESSION_ID): cv.string})
_COMPLETE_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_REPS): vol.All(vol.Coerce(int), vol.Range(min=0))}
)


def _get_runtime(hass: HomeAssistant) -> RuntimeManager:
    """Return the runtime manager for the loaded singleton entry."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("Training Buddy is not set up")
    return entries[0].runtime_data


def async_setup_services(hass: HomeAssistant) -> None:
    """Register all Training Buddy services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_START_SESSION):
        return

    async def _start(call: ServiceCall) -> None:
        runtime = _get_runtime(call.hass)
        try:
            await runtime.async_start_session(call.data[ATTR_SESSION_ID])
        except SessionError as err:
            raise ServiceValidationError(str(err)) from err

    async def _complete(call: ServiceCall) -> None:
        runtime = _get_runtime(call.hass)
        try:
            await runtime.async_complete_exercise(call.data.get(ATTR_REPS))
        except SessionError as err:
            raise ServiceValidationError(str(err)) from err

    def _simple(method_name: str):
        async def _handler(call: ServiceCall) -> None:
            runtime = _get_runtime(call.hass)
            try:
                await getattr(runtime, method_name)()
            except SessionError as err:
                raise ServiceValidationError(str(err)) from err

        return _handler

    hass.services.async_register(
        DOMAIN, SERVICE_START_SESSION, _start, schema=_START_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPLETE_EXERCISE, _complete, schema=_COMPLETE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PAUSE_SESSION, _simple("async_pause_session")
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME_SESSION, _simple("async_resume_session")
    )
    hass.services.async_register(
        DOMAIN, SERVICE_STOP_SESSION, _simple("async_stop_session")
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SKIP_EXERCISE, _simple("async_skip_exercise")
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CONTINUE_CIRCUIT, _simple("async_continue_circuit")
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove services when the last entry unloads."""
    # Only remove if no entries remain loaded.
    if hass.config_entries.async_loaded_entries(DOMAIN):
        return
    for service in (
        SERVICE_START_SESSION,
        SERVICE_PAUSE_SESSION,
        SERVICE_RESUME_SESSION,
        SERVICE_STOP_SESSION,
        SERVICE_COMPLETE_EXERCISE,
        SERVICE_SKIP_EXERCISE,
        SERVICE_CONTINUE_CIRCUIT,
    ):
        hass.services.async_remove(DOMAIN, service)
