"""Sensor platform for Training Buddy.

Two groups of sensors:

* **Controller sensors** reflect the live session (current exercise, progress,
  loop count, ...). They read the coordinator snapshot.
* **Exercise statistics sensors** are created per exercise device and read the
  statistics engine. They are added dynamically as exercises are created.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import TrainingBuddyConfigEntry
from .const import REPETITION_EXERCISE_TYPES, SIGNAL_EXERCISES_CHANGED
from .coordinator import TrainingBuddyCoordinator
from .entity import ControllerEntity, ExerciseEntity
from .models import Exercise
from .runtime import PHASE_LABELS, RuntimeManager
from .statistics import ExerciseStats


# -- controller sensors -------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class ControllerSensorDescription(SensorEntityDescription):
    """Describes a controller sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]


def _phase_label(snapshot: dict[str, Any]) -> StateType:
    phase = snapshot.get("phase")
    if phase is None:
        return None
    return PHASE_LABELS.get(phase, phase)


CONTROLLER_SENSORS: tuple[ControllerSensorDescription, ...] = (
    ControllerSensorDescription(
        key="current_exercise",
        translation_key="current_exercise",
        name="Current Exercise",
        icon="mdi:dumbbell",
        value_fn=lambda s: s.get("current_exercise_name"),
    ),
    ControllerSensorDescription(
        key="current_round",
        translation_key="current_round",
        name="Current Round",
        icon="mdi:format-list-numbered",
        value_fn=_phase_label,
    ),
    ControllerSensorDescription(
        key="session_progress",
        translation_key="session_progress",
        name="Session Progress",
        icon="mdi:progress-check",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("progress_pct", 0),
    ),
    ControllerSensorDescription(
        key="circuit_loop_count",
        translation_key="circuit_loop_count",
        name="Circuit Loop Count",
        icon="mdi:rotate-right",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("loop_count", 0),
    ),
    ControllerSensorDescription(
        key="active_session_name",
        translation_key="active_session_name",
        name="Active Session Name",
        icon="mdi:clipboard-text",
        value_fn=lambda s: s.get("session_name"),
    ),
    ControllerSensorDescription(
        key="session_status",
        translation_key="session_status",
        name="Session Status",
        icon="mdi:state-machine",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "idle",
            "running",
            "paused",
            "awaiting_continue",
            "completed",
        ],
        value_fn=lambda s: s.get("status"),
    ),
)


class ControllerSensor(ControllerEntity, SensorEntity):
    """A live session sensor on the controller device."""

    entity_description: ControllerSensorDescription

    def __init__(
        self,
        coordinator: TrainingBuddyCoordinator,
        description: ControllerSensorDescription,
    ) -> None:
        """Initialize the controller sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the sensor value from the snapshot."""
        return self.entity_description.value_fn(self.snapshot)


# -- exercise statistics sensors ----------------------------------------------
def _last_completed(stats: ExerciseStats) -> datetime | None:
    if stats.last_completed is None:
        return None
    return dt_util.parse_datetime(stats.last_completed)


@dataclass(frozen=True, kw_only=True)
class ExerciseStatDescription(SensorEntityDescription):
    """Describes an exercise statistic sensor."""

    value_fn: Callable[[ExerciseStats, datetime], StateType | datetime]
    applies_to: Callable[[str], bool]


_DURATION_KW = {
    "native_unit_of_measurement": UnitOfTime.SECONDS,
    "device_class": SensorDeviceClass.DURATION,
}

EXERCISE_STAT_SENSORS: tuple[ExerciseStatDescription, ...] = (
    ExerciseStatDescription(
        key="times_completed",
        translation_key="times_completed",
        name="Times Completed",
        icon="mdi:check-all",
        state_class=SensorStateClass.TOTAL_INCREASING,
        applies_to=lambda _t: True,
        value_fn=lambda st, _now: st.times_completed,
    ),
    ExerciseStatDescription(
        key="last_completed",
        translation_key="last_completed",
        name="Last Completed",
        device_class=SensorDeviceClass.TIMESTAMP,
        applies_to=lambda _t: True,
        value_fn=lambda st, _now: _last_completed(st),
    ),
    ExerciseStatDescription(
        key="longest_streak",
        translation_key="longest_streak",
        name="Longest Streak",
        icon="mdi:fire",
        native_unit_of_measurement="d",
        applies_to=lambda _t: True,
        value_fn=lambda st, _now: st.longest_streak,
    ),
    # repetition-only
    ExerciseStatDescription(
        key="total_reps",
        translation_key="total_reps",
        name="Total Reps",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        applies_to=lambda t: t in REPETITION_EXERCISE_TYPES,
        value_fn=lambda st, _now: st.total_reps,
    ),
    ExerciseStatDescription(
        key="personal_best",
        translation_key="personal_best",
        name="Personal Best",
        icon="mdi:trophy",
        applies_to=lambda t: t in REPETITION_EXERCISE_TYPES,
        value_fn=lambda st, _now: st.personal_best_reps,
    ),
    ExerciseStatDescription(
        key="weekly_reps",
        translation_key="weekly_reps",
        name="Weekly Reps",
        icon="mdi:calendar-week",
        applies_to=lambda t: t in REPETITION_EXERCISE_TYPES,
        value_fn=lambda st, now: st.reps_in_last_days(7, now),
    ),
    ExerciseStatDescription(
        key="monthly_reps",
        translation_key="monthly_reps",
        name="Monthly Reps",
        icon="mdi:calendar-month",
        applies_to=lambda t: t in REPETITION_EXERCISE_TYPES,
        value_fn=lambda st, now: st.reps_in_last_days(30, now),
    ),
    # duration-only
    ExerciseStatDescription(
        key="total_duration",
        translation_key="total_duration",
        name="Total Duration",
        icon="mdi:timer-sand",
        state_class=SensorStateClass.TOTAL_INCREASING,
        applies_to=lambda t: t not in REPETITION_EXERCISE_TYPES,
        value_fn=lambda st, _now: st.total_seconds,
        **_DURATION_KW,
    ),
    ExerciseStatDescription(
        key="longest_duration",
        translation_key="longest_duration",
        name="Longest Duration",
        icon="mdi:timer",
        applies_to=lambda t: t not in REPETITION_EXERCISE_TYPES,
        value_fn=lambda st, _now: st.longest_seconds,
        **_DURATION_KW,
    ),
)


class ExerciseStatSensor(ExerciseEntity, SensorEntity):
    """A statistics sensor on an exercise device."""

    entity_description: ExerciseStatDescription

    def __init__(
        self,
        coordinator: TrainingBuddyCoordinator,
        exercise: Exercise,
        description: ExerciseStatDescription,
    ) -> None:
        """Initialize the statistic sensor."""
        super().__init__(coordinator, exercise, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the statistic value, computing windows against now."""
        stats = self.coordinator.runtime.stats.get(self._exercise.id)
        return self.entity_description.value_fn(stats, dt_util.utcnow())


def _build_exercise_sensors(
    coordinator: TrainingBuddyCoordinator, exercise: Exercise
) -> list[ExerciseStatSensor]:
    return [
        ExerciseStatSensor(coordinator, exercise, desc)
        for desc in EXERCISE_STAT_SENSORS
        if desc.applies_to(exercise.type)
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrainingBuddyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Training Buddy sensors."""
    runtime: RuntimeManager = entry.runtime_data
    coordinator = runtime.coordinator

    entities: list[SensorEntity] = [
        ControllerSensor(coordinator, desc) for desc in CONTROLLER_SENSORS
    ]
    known: set[str] = set()
    for exercise in runtime.definitions.exercises.values():
        entities.extend(_build_exercise_sensors(coordinator, exercise))
        known.add(exercise.id)
    async_add_entities(entities)

    @callback
    def _add_new_exercises() -> None:
        new_entities: list[SensorEntity] = []
        for exercise in runtime.definitions.exercises.values():
            if exercise.id in known:
                continue
            new_entities.extend(_build_exercise_sensors(coordinator, exercise))
            known.add(exercise.id)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_EXERCISES_CHANGED, _add_new_exercises
        )
    )
