import time
from collections import defaultdict
from typing import Dict, List, Optional, Any
from src.domain.events import Event

class OutletAggregator:
    def __init__(self, outlet_id: str, absent_seconds: int, target_spg_ids: List[str] | None = None):
        self.outlet_id = outlet_id
        self.absent_seconds = absent_seconds
        
        # spg_id -> last_seen_timestamp (global max)
        self.last_seen: Dict[str, float] = defaultdict(float)
        
        # spg_id -> bool (is currently marked absent?)
        self.is_absent: Dict[str, bool] = defaultdict(bool)
        
        # Anti-spam: spg_id -> bool (has alert been fired for this absence period?)
        self.alert_fired: Dict[str, bool] = defaultdict(bool)

        # Startup Logic
        self.start_time = time.time()
        self.target_spg_ids = target_spg_ids or []
        # Mark all targets as initially "never seen" (last_seen=0)
        
        # spg_id -> name (cache)
        self.spg_names: Dict[str, str] = {}

    def ingest_events(self, events: List[Event]):
        """
        Ingest a batch of events from any camera in this outlet.
        Update global last_seen for relevant SPGs.
        """
        for e in events:
            if e.outlet_id != self.outlet_id:
                continue
            
            if e.event_type == "SPG_SEEN":
                if e.spg_id:
                    self._update_seen(e.spg_id, e.ts)
                    if e.name:
                        self.spg_names[e.spg_id] = e.name

    def _update_seen(self, spg_id: str, ts: float):
        # Update global last seen
        if ts > self.last_seen[spg_id]:
            self.last_seen[spg_id] = ts
            
            # Only reset absence if this is new information
            if self.is_absent[spg_id]:
                self.is_absent[spg_id] = False
                self.alert_fired[spg_id] = False
                # We could emit a SPG_GLOBAL_PRESENT event here if needed

    def tick(self) -> List[Event]:
        """
        Evaluate global absence rules.
        Returns list of ABSENT_ALERT_FIRED events if any.
        """
        now = time.time()
        generated_events = []

        # 1. Check Registered Targets (Startup / Never Arrived Logic)
        for spg_id in self.target_spg_ids:
            last_ts = self.last_seen[spg_id]
            
            # Case A: Never Seen (Startup Absence)
            if last_ts == 0:
                # Check if we are past the grace period since startup
                if (now - self.start_time) > self.absent_seconds:
                    if not self.is_absent[spg_id]:
                         self.is_absent[spg_id] = True
                    
                    if not self.alert_fired[spg_id]:
                        self.alert_fired[spg_id] = True
                        evt = Event(
                            ts=now,
                            event_type="ABSENT_ALERT_FIRED",
                            outlet_id=self.outlet_id,
                            camera_id="aggregator",
                            spg_id=spg_id,
                            details={
                                "reason": "startup_absence_never_arrived",
                                "seconds_since_startup": int(now - self.start_time)
                            }
                        )
                        generated_events.append(evt)
                continue

            # Case B: Seen Before (Regular Absence)
            time_diff = now - last_ts
            
            if time_diff > self.absent_seconds:
                if not self.is_absent[spg_id]:
                    self.is_absent[spg_id] = True
                
                if not self.alert_fired[spg_id]:
                    self.alert_fired[spg_id] = True
                    evt = Event(
                        ts=now,
                        event_type="ABSENT_ALERT_FIRED",
                        outlet_id=self.outlet_id,
                        camera_id="aggregator",
                        spg_id=spg_id,
                        name=self.spg_names.get(spg_id),
                        details={
                            "reason": "global_absence",
                            "seconds_since_last_seen": int(time_diff)
                        }
                    )
                    generated_events.append(evt)
        
        return generated_events

    def get_state(self) -> Dict[str, Any]:
        """
        Return current state of all tracked SPGs.
        """
        now = time.time()
        state = {
            "outlet_id": self.outlet_id,
            "timestamp": now,
            "spgs": []
        }
        
        for spg_id in self.target_spg_ids:
            last_ts = self.last_seen[spg_id]
            is_absent = self.is_absent[spg_id]
            # Determine status
            status = "PRESENT"
            if last_ts == 0:
                # Check if absent period passed since startup
                if (now - self.start_time) > self.absent_seconds:
                    status = "NEVER_ARRIVED"
                else:
                    status = "NOT_SEEN_YET"
            elif is_absent:
                status = "ABSENT"
            
            # Duration calculation
            if last_ts == 0:
                duration = int(now - self.start_time)
            else:
                duration = int(now - last_ts)

            spg_data = {
                "id": spg_id,
                "name": self.spg_names.get(spg_id, "Unknown"),
                "status": status,
                "last_seen_ts": last_ts,
                "seconds_since_last_event": duration,
                "is_alert_fired": self.alert_fired[spg_id]
            }
            state["spgs"].append(spg_data)
            
        return state

    def dump_state(self, filepath: str):
        """
        Write current state to a JSON file (Windows-safe).
        """
        import json
        
        state = self.get_state()
        
        # Direct write (Windows-safe, avoids os.replace lock issues)
        for attempt in range(3):
            try:
                with open(filepath, 'w') as f:
                    json.dump(state, f, indent=2)
                return  # Success
            except PermissionError:
                # File might be locked by dashboard reader, retry after short wait
                time.sleep(0.05)
        
        # If all retries fail, silently skip this tick
        # (dashboard will just show slightly stale data)
