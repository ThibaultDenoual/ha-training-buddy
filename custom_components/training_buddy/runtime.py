"""Runtime manager for Training Buddy.

The runtime manager is the single bridge between the pure domain engines
(:mod:`session_engine`, :mod:`statistics`) and Home Assistant. It owns:

* the loaded :class:`~.models.Definitions`,
* the :class:`~.session_engine.SessionEngine` (active session),
* the :class:`~.statistics.StatisticsEngine`,
* persistence through :class:`~.storage.TrainingBuddyStore`,
* the wall-clock timer used purely for UI/notifications, and
* the snapshot pushed to the :class:`~.coordinator.TrainingBuddyCoordinator`.

All session mutations funnel through here so that every action is persisted,
reflected to entities, and announced on the event bus in one place.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time

from .const import (
    DOMAIN,
    PHASE_CIRCUIT,
    PHASE_WARMUP,
    SIGNAL_EXERCISES_CHANGED,
    STATUS_IDLE,
    STATUS_PAUSED,
    STATUS_RUNNING,
)
from .coordinator import TrainingBuddyCoordinator
from .models import Definitions, Exercise, Round, Session
from .session_engine import PlanEntry, SessionEngine, SessionError
from .statistics import StatisticsEngine
from .storage import TrainingBuddyStore

_LOGGER = logging.getLogger(__name__)

EVENT_EXERCISE_COMPLETED = f"{DOMAIN}_exercise_completed"
EVENT_SESSION_CHANGED = f"{DOMAIN}_session_changed"
EVENT_TIMER_FINISHED = f"{DOMAIN}_timer_finished"

# Human-readable labels for phases, used by entities. Defined here so the
# mapping lives in one place.
PHASE_LABELS = {PHASE_WARMUP: "Warm-up", PHASE_CIRCUIT: "Circuit"}


class RuntimeManager:
    """Owns engines, persistence and HA wiring for a config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: TrainingBuddyStore,
        coordinator: TrainingBuddyCoordinator,
    ) -> None:
        """Create the runtime manager."""
        self.hass = hass
        self.store = store
        self.coordinator = coordinator
        self.definitions = Definitions()
        self.engine = SessionEngine(now=dt_util.utcnow)
        self.stats = StatisticsEngine()
        self._timer_unsub: CALLBACK_TYPE | None = None
        self._lock = asyncio.Lock()

    # -- lifecycle ------------------------------------------------------------
    async def async_setup(self) -> None:
        """Load persisted state and restore any active session."""
        self.definitions = await self.store.async_load_definitions()
        self.stats = await self.store.async_load_statistics()
        restored = await self.store.async_load_runtime()
        if restored is not None:
            _LOGGER.info(
                "Restoring active session %s (%s)",
                restored.session_name,
                restored.status,
            )
            self.engine.load(restored)
            self._schedule_timer()
        self.coordinator.async_set_updated_data(self.build_snapshot())

    async def async_unload(self) -> None:
        """Cancel the timer on unload (state is already persisted)."""
        self._cancel_timer()

    # -- snapshot -------------------------------------------------------------
    def build_snapshot(self) -> dict[str, Any]:
        """Build the entity-facing view of the current state."""
        state = self.engine.state
        if state is None:
            return {
                "active": False,
                "paused": False,
                "running": False,
                "status": STATUS_IDLE,
                "session_name": None,
                "current_exercise_id": None,
                "current_exercise_name": None,
                "current_exercise_type": None,
                "current_target_reps": None,
                "current_target_seconds": None,
                "phase": None,
                "progress_pct": 0,
                "loop_count": 0,
                "current_loop": 0,
                "entry_index": 0,
                "phase_total": 0,
                "timer_ends_at": None,
            }

        entry = state.current_entry
        return {
            "active": True,
            "paused": state.status == STATUS_PAUSED,
            "running": state.status == STATUS_RUNNING,
            "status": state.status,
            "session_name": state.session_name,
            "current_exercise_id": entry.exercise_id if entry else None,
            "current_exercise_name": entry.exercise_name if entry else None,
            "current_exercise_type": entry.exercise_type if entry else None,
            "current_target_reps": entry.target_reps if entry else None,
            "current_target_seconds": entry.target_seconds if entry else None,
            "phase": state.phase,
            "progress_pct": state.progress_pct,
            "loop_count": state.loop_count,
            "current_loop": state.current_loop,
            "entry_index": state.entry_index,
            "phase_total": state.phase_total,
            "timer_ends_at": state.timer_ends_at,
        }

    def _push(self) -> None:
        self.coordinator.async_set_updated_data(self.build_snapshot())

    # -- session control ------------------------------------------------------
    async def async_start_session(self, session_id: str) -> None:
        """Start the named session."""
        async with self._lock:
            session = self.definitions.sessions.get(session_id)
            if session is None:
                raise SessionError(f"Unknown session: {session_id}")
            warmup, circuit = self._build_plan(session)
            self.engine.start(session.id, session.name, warmup, circuit)
            await self._after_change()

    async def async_pause_session(self) -> None:
        """Pause the active session."""
        async with self._lock:
            self.engine.pause()
            await self._after_change()

    async def async_resume_session(self) -> None:
        """Resume the active session."""
        async with self._lock:
            self.engine.resume()
            await self._after_change()

    async def async_stop_session(self) -> None:
        """Stop and clear the active session."""
        async with self._lock:
            self.engine.stop()
            await self._after_change()

    async def async_complete_exercise(self, reps: int | None = None) -> None:
        """Complete the current exercise and record statistics."""
        async with self._lock:
            event = self.engine.complete_exercise(reps)
            self.stats.apply(event)
            await self.store.async_save_statistics(self.stats)
            self.hass.bus.async_fire(
                EVENT_EXERCISE_COMPLETED,
                {
                    "exercise_id": event.exercise_id,
                    "exercise_type": event.exercise_type,
                    "reps": event.reps,
                    "seconds": event.seconds,
                },
            )
            await self._after_change()

    async def async_skip_exercise(self) -> None:
        """Skip the current exercise."""
        async with self._lock:
            self.engine.skip_exercise()
            await self._after_change()

    async def async_continue_circuit(self) -> None:
        """Begin another circuit loop."""
        async with self._lock:
            self.engine.continue_circuit()
            await self._after_change()

    async def _after_change(self) -> None:
        """Persist runtime state, reschedule timer, push and notify."""
        await self.store.async_save_runtime(self.engine.state)
        self._schedule_timer()
        self._push()
        self.hass.bus.async_fire(
            EVENT_SESSION_CHANGED, {"status": self.build_snapshot()["status"]}
        )

    # -- timer ----------------------------------------------------------------
    def _cancel_timer(self) -> None:
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None

    def _schedule_timer(self) -> None:
        """(Re)schedule the informational timer for the current entry.

        The timer never completes an exercise; it only fires an event and
        refreshes entities so a card can react when the target time elapses.
        """
        self._cancel_timer()
        state = self.engine.state
        if state is None or state.timer_ends_at is None:
            return
        if state.status != STATUS_RUNNING:
            return
        ends_at = datetime.fromisoformat(state.timer_ends_at)
        self._timer_unsub = async_track_point_in_time(
            self.hass, self._on_timer_finished, ends_at
        )

    async def _on_timer_finished(self, _now: datetime) -> None:
        self._timer_unsub = None
        self.hass.bus.async_fire(EVENT_TIMER_FINISHED, {})
        self._push()

    # -- plan building --------------------------------------------------------
    def _build_plan(
        self, session: Session
    ) -> tuple[list[PlanEntry], list[PlanEntry]]:
        warmup = self._resolve_round(session.warmup_round_id)
        circuit = self._resolve_round(session.circuit_round_id)
        return warmup, circuit

    def _resolve_round(self, round_id: str | None) -> list[PlanEntry]:
        if round_id is None:
            return []
        rnd = self.definitions.rounds.get(round_id)
        if rnd is None:
            return []
        plan: list[PlanEntry] = []
        for entry in rnd.entries:
            exercise = self.definitions.exercises.get(entry.exercise_id)
            if exercise is None:
                continue  # tolerate a deleted exercise
            plan.append(
                PlanEntry(
                    exercise_id=exercise.id,
                    exercise_name=exercise.name,
                    exercise_type=exercise.type,
                    target_reps=entry.target_reps,
                    target_seconds=entry.target_seconds,
                )
            )
        return plan

    # -- definitions CRUD (used by options flow) ------------------------------
    async def async_add_exercise(self, exercise: Exercise) -> Exercise:
        """Add an exercise and announce the structural change."""
        self.definitions.add_exercise(exercise)
        await self.store.async_save_definitions(self.definitions)
        self._notify_exercises_changed()
        return exercise

    async def async_remove_exercise(self, exercise_id: str) -> None:
        """Remove an exercise and its statistics."""
        self.definitions.remove_exercise(exercise_id)
        self.stats.remove(exercise_id)
        await self.store.async_save_definitions(self.definitions)
        await self.store.async_save_statistics(self.stats)
        self._notify_exercises_changed()

    async def async_add_round(self, rnd: Round) -> Round:
        """Add a round definition."""
        self.definitions.validate_round_entries(rnd)
        self.definitions.add_round(rnd)
        await self.store.async_save_definitions(self.definitions)
        return rnd

    async def async_remove_round(self, round_id: str) -> None:
        """Remove a round definition."""
        self.definitions.remove_round(round_id)
        await self.store.async_save_definitions(self.definitions)

    async def async_add_session(self, session: Session) -> Session:
        """Add a session definition."""
        self.definitions.add_session(session)
        await self.store.async_save_definitions(self.definitions)
        return session

    async def async_remove_session(self, session_id: str) -> None:
        """Remove a session definition."""
        self.definitions.remove_session(session_id)
        await self.store.async_save_definitions(self.definitions)

    def _notify_exercises_changed(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_EXERCISES_CHANGED)
        self._push()
