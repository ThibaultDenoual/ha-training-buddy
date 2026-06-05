"""Config and options flow for Training Buddy.

The config flow is intentionally tiny: Training Buddy is a singleton, so the
flow just creates the one entry (``single_config_entry`` in the manifest stops
a second one from being added).

All domain management — exercises, rounds and sessions — happens in the
**options flow**, which is a menu-driven CRUD interface. The options flow reads
and writes the runtime manager (and therefore Storage) directly; it never puts
domain data into the config entry. This keeps the entry trivial and the domain
data in the right place.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import selector

from .const import (
    ALL_EXERCISE_TYPES,
    DOMAIN,
    EXERCISE_TYPE_REPETITION,
    SINGLETON_ENTRY_TITLE,
)
from .models import (
    DEFAULT_TARGET_REPS,
    Exercise,
    Round,
    RoundEntry,
    Session,
    ValidationError,
)
from .runtime import RuntimeManager


class TrainingBuddyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the (singleton) config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single config entry."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title=SINGLETON_ENTRY_TITLE, data={})

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TrainingBuddyOptionsFlow:
        """Return the options flow."""
        return TrainingBuddyOptionsFlow()


def _exercise_type_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=sorted(ALL_EXERCISE_TYPES),
            translation_key="exercise_type",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _options_selector(
    items: dict[str, str],
) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=key, label=label)
                for key, label in items.items()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _name_map(items) -> dict[str, str]:
    """Return an {id: name} mapping for a collection of named objects."""
    return {item.id: item.name for item in items}


class TrainingBuddyOptionsFlow(OptionsFlow):
    """Menu-driven CRUD over exercises, rounds and sessions."""

    @property
    def runtime(self) -> RuntimeManager:
        """Return the runtime manager for the loaded entry."""
        return self.config_entry.runtime_data

    # -- main menu ------------------------------------------------------------
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the top-level management menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_exercise",
                "delete_exercise",
                "add_round",
                "add_round_entry",
                "delete_round",
                "add_session",
                "delete_session",
                "finish",
            ],
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Close the options flow."""
        return self.async_create_entry(title="", data={})

    # -- exercises ------------------------------------------------------------
    async def async_step_add_exercise(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add an exercise definition."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                exercise = Exercise(
                    name=user_input["name"], type=user_input["type"]
                )
            except ValidationError:
                errors["name"] = "invalid_name"
            else:
                await self.runtime.async_add_exercise(exercise)
                return await self.async_step_init()
        return self.async_show_form(
            step_id="add_exercise",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required(
                        "type", default=EXERCISE_TYPE_REPETITION
                    ): _exercise_type_selector(),
                }
            ),
            errors=errors,
        )

    async def async_step_delete_exercise(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete an exercise definition."""
        items = {
            e.id: e.name for e in self.runtime.definitions.exercises.values()
        }
        if not items:
            return await self.async_step_init()
        if user_input is not None:
            await self.runtime.async_remove_exercise(user_input["exercise_id"])
            return await self.async_step_init()
        return self.async_show_form(
            step_id="delete_exercise",
            data_schema=vol.Schema(
                {vol.Required("exercise_id"): _options_selector(items)}
            ),
        )

    # -- rounds ---------------------------------------------------------------
    async def async_step_add_round(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create an (initially empty) round."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                rnd = Round(name=user_input["name"])
            except ValidationError:
                errors["name"] = "invalid_name"
            else:
                await self.runtime.async_add_round(rnd)
                return await self.async_step_init()
        return self.async_show_form(
            step_id="add_round",
            data_schema=vol.Schema({vol.Required("name"): str}),
            errors=errors,
        )

    async def async_step_add_round_entry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Append an exercise (with a target) to a round."""
        rounds = _name_map(self.runtime.definitions.rounds.values())
        exercises = {
            e.id: e.name for e in self.runtime.definitions.exercises.values()
        }
        if not rounds or not exercises:
            return await self.async_step_init()

        if user_input is not None:
            rnd = self.runtime.definitions.rounds[user_input["round_id"]]
            exercise = self.runtime.definitions.exercises[
                user_input["exercise_id"]
            ]
            target = int(user_input["target"])
            if exercise.is_repetition_based:
                entry = RoundEntry(exercise_id=exercise.id, target_reps=target)
            else:
                entry = RoundEntry(
                    exercise_id=exercise.id, target_seconds=target
                )
            rnd.entries.append(entry)
            await self.runtime.async_add_round(rnd)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="add_round_entry",
            data_schema=vol.Schema(
                {
                    vol.Required("round_id"): _options_selector(rounds),
                    vol.Required("exercise_id"): _options_selector(exercises),
                    vol.Required(
                        "target", default=DEFAULT_TARGET_REPS
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=3600,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )

    async def async_step_delete_round(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete a round definition."""
        items = _name_map(self.runtime.definitions.rounds.values())
        if not items:
            return await self.async_step_init()
        if user_input is not None:
            await self.runtime.async_remove_round(user_input["round_id"])
            return await self.async_step_init()
        return self.async_show_form(
            step_id="delete_round",
            data_schema=vol.Schema(
                {vol.Required("round_id"): _options_selector(items)}
            ),
        )

    # -- sessions -------------------------------------------------------------
    async def async_step_add_session(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a session from a warm-up and a circuit round."""
        rounds = _name_map(self.runtime.definitions.rounds.values())
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                session = Session(
                    name=user_input["name"],
                    warmup_round_id=user_input.get("warmup_round_id"),
                    circuit_round_id=user_input.get("circuit_round_id"),
                )
            except ValidationError:
                errors["name"] = "invalid_name"
            else:
                await self.runtime.async_add_session(session)
                return await self.async_step_init()

        schema: dict[Any, Any] = {vol.Required("name"): str}
        if rounds:
            round_sel = _options_selector(rounds)
            schema[vol.Optional("warmup_round_id")] = round_sel
            schema[vol.Optional("circuit_round_id")] = round_sel
        return self.async_show_form(
            step_id="add_session",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_delete_session(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete a session definition."""
        items = {
            s.id: s.name for s in self.runtime.definitions.sessions.values()
        }
        if not items:
            return await self.async_step_init()
        if user_input is not None:
            await self.runtime.async_remove_session(user_input["session_id"])
            return await self.async_step_init()
        return self.async_show_form(
            step_id="delete_session",
            data_schema=vol.Schema(
                {vol.Required("session_id"): _options_selector(items)}
            ),
        )
