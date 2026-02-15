from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.notification.telegram_notifier import TelegramNotifier
from src.storage.event_store import EventStore

@dataclass
class CamStream:
    data_dir: Path
    events_path: Path
    offset: int = 0
    last_read_ts: float = 0.0


class OutletAggregator:
    """
    Minimal aggregator:
    - reads SPG_SEEN events from multiple camera data_dirs
    - computes last_seen_global = max across cameras
    - fires ABSENT alert once per SPG until seen again
    """

    def __init__(
        self,
        outlet_id: str,
        data_dirs: List[str],
        absent_seconds: int,
        poll_interval_sec: float = 1.0,
        out_data_dir: Optional[str] = None,
    ):
        self.outlet_id = outlet_id
        self.absent_seconds = int(absent_seconds)
        self.poll_interval_sec = float(poll_interval_sec)

        self.cams: List[CamStream] = []
        for d in data_dirs:
            p = Path(d)
            self.cams.append(
                CamStream(
                    data_dir=p,
                    events_path=p / "events.jsonl",
                    offset=0,
                    last_read_ts=0.0,
                )
            )

        # global state per spg
        self.last_seen_global: Dict[str, float] = {}
        self.last_name_global: Dict[str, str] = {}
        self.alert_active: Dict[str, bool] = {}

        # output event store (aggregator-level)
        self.out_store = EventStore(out_data_dir or f"./data_outlet_{outlet_id}")

        # telegram
        self.notifier = None
        try:
            self.notifier = TelegramNotifier.from_env()
        except Exception as e:
            print("[WARN] Telegram notifier disabled:", e)

    def _tail_events(self, cam: CamStream):
        """
        Read new lines only (incremental) from cam.events.jsonl.
        Keeps offset in memory.
        """
        if not cam.events_path.exists():
            return

        try:
            with open(cam.events_path, "r", encoding="utf-8") as f:
                f.seek(cam.offset)
                while True:
                    line = f.readline()
                    if not line:
                        break

                    cam.last_read_ts = time.time()
                    cam.offset = f.tell()

                    line = line.strip()
                    if not line:
                        continue

                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue

                    if ev.get("event_type") != "SPG_SEEN":
                        continue

                    spg_id = ev.get("spg_id")
                    ts = float(ev.get("ts", 0))
                    name = ev.get("name") or ""

                    if not spg_id or ts <= 0:
                        continue

                    # update global last_seen
                    prev = self.last_seen_global.get(spg_id, 0.0)
                    if ts > prev:
                        self.last_seen_global[spg_id] = ts
                        if name:
                            self.last_name_global[spg_id] = name

        except Exception as e:
            print(f"[WARN] Failed reading {cam.events_path}: {e}")

    def _fire_alert(self, spg_id: str, seconds_since: int):
        name = self.last_name_global.get(spg_id, "")
        text = (
            f"⚠️ SPG ABSENT ALERT (OUTLET)\n"
            f"Outlet: {self.outlet_id}\n"
            f"SPG: {name or spg_id}\n"
            f"Last seen: {seconds_since}s ago"
        )

        # write aggregator event
        self.out_store.append(
            # keep same Event model? if your EventStore expects Pydantic Event, adjust here.
            # If your EventStore expects Event model, replace dict with Event(...)
            # For minimal: EventStore in your project currently expects Event.model_dump()
            # so safest is to import Event and construct it.
            __import__("src.domain.events", fromlist=["Event"]).Event(
                ts=time.time(),
                event_type="ABSENT_ALERT_FIRED",
                outlet_id=self.outlet_id,
                camera_id="OUTLET_AGG",
                spg_id=spg_id,
                name=name or None,
                similarity=None,
                details={"seconds_since_last_seen": seconds_since},
            )
        )

        print("[OUTLET_ALERT]", text.replace("\n", " | "))

        if self.notifier:
            try:
                self.notifier.send_message(text)
            except Exception as e:
                print("[ERROR] Telegram send failed:", e)

    def run(self, target_spg_ids: List[str]):
        print(f"[AGG] OutletAggregator started outlet={self.outlet_id}")
        print(f"[AGG] Cameras: {[str(c.data_dir) for c in self.cams]}")
        print(f"[AGG] Target SPGs: {target_spg_ids}")
        print(f"[AGG] absent_seconds={self.absent_seconds}")

        # init alert_active map
        for sid in target_spg_ids:
            self.alert_active.setdefault(sid, False)

        while True:
            now = time.time()

            # read incremental events from all cameras
            for cam in self.cams:
                self._tail_events(cam)

            # decide global presence per spg
            for sid in target_spg_ids:
                last = self.last_seen_global.get(sid)

                if last is None:
                    # belum pernah terlihat sama sekali → jangan alert dulu (biar nggak spam saat startup)
                    continue

                dt = now - last

                if dt > self.absent_seconds:
                    if not self.alert_active.get(sid, False):
                        self._fire_alert(sid, int(dt))
                        self.alert_active[sid] = True
                else:
                    self.alert_active[sid] = False

            time.sleep(self.poll_interval_sec)