from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from src.domain.events import Event

@dataclass
class SpgState:
    state: str = "UNKNOWN" # Ada unknown, present, absent
    last_seen_ts: Optional[float] = None
    alert_active: bool = False

class PresenceEngine:
    def __init__(
        self,
        outlet_id: str,
        camera_id: str,
        grace_seconds: int,
        absent_seconds: int,
    ):
        self.outlet_id = outlet_id
        self.camera_id = camera_id
        self.grace_seconds = int(grace_seconds)
        self.absent_seconds = int(absent_seconds)
        self._states: dict[str, SpgState] = {}

    def _get(self, spg_id: str) -> SpgState:
        if spg_id not in self._states:
            self._states[spg_id] = SpgState()
        return self._states[spg_id]

    def observe_seen(
        self,
        spg_id: str,
        name: str | None,
        similarity: float | None,
        ts: float | None = None,
    ) -> list[Event]:
        """Call this when SPG is matched (valid identity)."""
        now = ts if ts is not None else time.time()
        s = self._get(spg_id)

        events: list[Event] = []

        s.last_seen_ts = now

        events.append(
            Event(
                ts=now,
                event_type="SPG_SEEN",
                outlet_id=self.outlet_id,
                camera_id=self.camera_id,
                spg_id=spg_id,
                name=name,
                similarity=similarity,
                details={},
            )
        )

        if s.state != "PRESENT":
            s.state = "PRESENT"
            s.alert_active = False
            events.append(
                Event(
                    ts=now,
                    event_type="SPG_PRESENT",
                    outlet_id=self.outlet_id,
                    camera_id=self.camera_id,
                    spg_id=spg_id,
                    name=name,
                    similarity=similarity,
                    details={},
                )
            )

        return events

    def tick(self, target_spg_ids: list[str], ts: float | None = None) -> list[Event]:
        """
        Call periodically to evaluate absence.
        It will:
        - set ABSENT when now-last_seen > grace_seconds (on transition)
        - fire ABSENT_ALERT_FIRED when now-last_seen > absent_seconds (once per absence period)
        """
        now = ts if ts is not None else time.time()
        events: list[Event] = []

        for spg_id in target_spg_ids:
            s = self._get(spg_id)

            if s.last_seen_ts is None:
                continue

            dt = now - s.last_seen_ts

            if dt > self.grace_seconds and s.state != "ABSENT":
                s.state = "ABSENT"
                events.append(
                    Event(
                        ts=now,
                        event_type="SPG_ABSENT",
                        outlet_id=self.outlet_id,
                        camera_id=self.camera_id,
                        spg_id=spg_id,
                        details={"seconds_since_last_seen": int(dt)},
                    )
                )

            if dt > self.absent_seconds and not s.alert_active:
                s.alert_active = True
                events.append(
                    Event(
                        ts=now,
                        event_type="ABSENT_ALERT_FIRED",
                        outlet_id=self.outlet_id,
                        camera_id=self.camera_id,
                        spg_id=spg_id,
                        details={"seconds_since_last_seen": int(dt)},
                    )
                )

        return events