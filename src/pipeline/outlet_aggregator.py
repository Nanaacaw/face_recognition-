import time
from collections import defaultdict
from typing import Dict, List, Optional
from src.domain.events import Event

class OutletAggregator:
    def __init__(self, outlet_id: str, absent_seconds: int):
        self.outlet_id = outlet_id
        self.absent_seconds = absent_seconds
        
        # spg_id -> last_seen_timestamp (global max)
        self.last_seen: Dict[str, float] = defaultdict(float)
        
        # spg_id -> bool (is currently marked absent?)
        self.is_absent: Dict[str, bool] = defaultdict(bool)
        
        # Anti-spam: spg_id -> bool (has alert been fired for this absence period?)
        self.alert_fired: Dict[str, bool] = defaultdict(bool)

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

    def _update_seen(self, spg_id: str, ts: float):
        # Update global last seen
        if ts > self.last_seen[spg_id]:
            self.last_seen[spg_id] = ts
            
        # If they were absent, they are now PRESENT
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

        for spg_id, last_ts in self.last_seen.items():
            # Skip if we never really saw them (or ts is 0)
            if last_ts == 0:
                continue

            time_diff = now - last_ts
            
            # Check absence
            if time_diff > self.absent_seconds:
                if not self.is_absent[spg_id]:
                    self.is_absent[spg_id] = True
                    # Transited to absent locally
                
                # Check if we need to fire alert
                if not self.alert_fired[spg_id]:
                    self.alert_fired[spg_id] = True
                    
                    # Create the global alert
                    evt = Event(
                        ts=now,
                        event_type="ABSENT_ALERT_FIRED",
                        outlet_id=self.outlet_id,
                        camera_id="aggregator", # Virtual camera id
                        spg_id=spg_id,
                        details={
                            "reason": "global_absence",
                            "seconds_since_last_seen": int(time_diff)
                        }
                    )
                    generated_events.append(evt)
        
        return generated_events
