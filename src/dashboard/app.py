"""
SPG Outlet Monitoring Dashboard
Real-time personnel monitoring powered by Streamlit.
"""
import streamlit as st
import json
import os
import time
import glob
from datetime import datetime
from collections import Counter

# ─────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SPG Monitoring",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─────────────────────────────────────────────
# Path Resolution
# ─────────────────────────────────────────────
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "sim_output")

# ─────────────────────────────────────────────
# Minimal CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1rem; }
    .status-live { color: #2ed573; font-weight: 600; }
    .status-off  { color: #ff4757; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def load_state(data_dir):
    state_file = os.path.join(data_dir, "outlet_state.json")
    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def load_events(data_dir, max_events=30):
    events = []
    for ef in glob.glob(os.path.join(data_dir, "cam_*", "events.jsonl")):
        try:
            cam_id = os.path.basename(os.path.dirname(ef))
            with open(ef, 'r') as f:
                for line in f.readlines()[-max_events:]:
                    if line.strip():
                        try:
                            d = json.loads(line)
                            d['_cam'] = cam_id
                            events.append(d)
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
    events.sort(key=lambda e: e.get('ts', 0), reverse=True)
    return events[:max_events]


def read_image_bytes(path):
    """Read image as bytes to avoid Streamlit MediaFileStorage caching issues."""
    try:
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                return f.read()
    except (PermissionError, FileNotFoundError):
        pass
    return None


def find_snapshot(data_dir, spg_id):
    files = glob.glob(os.path.join(data_dir, "cam_*", "snapshots", f"latest_{spg_id}.jpg"))
    if files:
        return max(files, key=os.path.getmtime)
    return None


def fmt_dur(seconds):
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, r = divmod(seconds, 3600)
        m, _ = divmod(r, 60)
        return f"{int(h)}h {int(m)}m"


# ─────────────────────────────────────────────
# Sidebar (compact)
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    data_dir = st.text_input("Data Dir", value=DEFAULT_DATA_DIR)
    refresh_rate = st.slider("Refresh (s)", 1, 10, 3)
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    show_events = st.checkbox("Show Events", value=True)
    show_cameras = st.checkbox("Show Camera Feed", value=False)

# ─────────────────────────────────────────────
# Load Data
# ─────────────────────────────────────────────
state = load_state(data_dir)

if not state:
    st.title("🏪 SPG Monitoring Dashboard")
    st.warning("Waiting for data... Start the simulation: `make simulate-light`")
    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()
    st.stop()

# Parse state
last_ts = state.get('timestamp', 0)
is_live = (time.time() - last_ts) < 10
outlet_id = state.get('outlet_id', 'Unknown')
spgs = state.get("spgs", [])
total = len(spgs)
counts = Counter(s['status'] for s in spgs)
present = counts.get('PRESENT', 0)
absent = counts.get('ABSENT', 0) + counts.get('NEVER_ARRIVED', 0)

# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
h1, h2 = st.columns([3, 1])
with h1:
    st.title(f"🏪 {outlet_id.upper().replace('_', ' ')}")
with h2:
    if is_live:
        st.markdown("### <span class='status-live'>🟢 LIVE</span>", unsafe_allow_html=True)
    else:
        st.markdown("### <span class='status-off'>🔴 OFFLINE</span>", unsafe_allow_html=True)
    st.caption(f"Updated: {datetime.fromtimestamp(last_ts).strftime('%H:%M:%S')}")

# ─────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total", total)
m2.metric("Present", present)
m3.metric("Absent", absent)
rate = f"{present/total*100:.0f}%" if total > 0 else "0%"
m4.metric("Attendance", rate)

st.divider()

# ─────────────────────────────────────────────
# Personnel Status
# ─────────────────────────────────────────────
st.subheader("👥 Personnel")

# Sort: absent first
priority = {"ABSENT": 0, "NEVER_ARRIVED": 1, "NOT_SEEN_YET": 2, "PRESENT": 3}
sorted_spgs = sorted(spgs, key=lambda s: priority.get(s['status'], 99))

STATUS_ICON = {
    "PRESENT": "🟢",
    "ABSENT": "🔴",
    "NEVER_ARRIVED": "🟠",
    "NOT_SEEN_YET": "⚪",
}

num_cols = min(4, max(2, len(sorted_spgs)))
cols = st.columns(num_cols)

for idx, spg in enumerate(sorted_spgs):
    with cols[idx % num_cols]:
        status = spg['status']
        name = spg.get('name', 'Unknown')
        spg_id = spg.get('id', '?')
        dur = spg.get('seconds_since_last_event', 0)
        icon = STATUS_ICON.get(status, "❓")
        
        st.markdown(f"**{icon} {name}** (`{spg_id}`)")
        st.caption(f"{status} • {fmt_dur(dur)}")
        
        # Show snapshot (read as bytes to prevent MediaFileStorageError)
        snap_path = find_snapshot(data_dir, spg_id)
        img_bytes = read_image_bytes(snap_path)
        if img_bytes:
            st.image(img_bytes, caption=f"Last seen", width="stretch")

# ─────────────────────────────────────────────
# Camera Feed (optional)
# ─────────────────────────────────────────────
if show_cameras:
    st.divider()
    st.subheader("📹 Camera Feeds")
    
    frame_files = sorted(glob.glob(os.path.join(data_dir, "cam_*", "snapshots", "latest_frame.jpg")))
    
    if not frame_files:
        st.info("No camera frames yet.")
    else:
        cam_cols = st.columns(min(2, len(frame_files)))
        for idx, fp in enumerate(frame_files):
            cam_name = os.path.basename(os.path.dirname(os.path.dirname(fp)))
            img_bytes = read_image_bytes(fp)
            with cam_cols[idx % len(cam_cols)]:
                if img_bytes:
                    st.image(img_bytes, caption=f"📷 {cam_name.upper()}", width="stretch")
                st.caption(f"[MJPEG Stream](http://localhost:8081/stream/{cam_name})")

# ─────────────────────────────────────────────
# Event Log (optional)
# ─────────────────────────────────────────────
if show_events:
    st.divider()
    st.subheader("📋 Recent Events")
    
    events = load_events(data_dir)
    if not events:
        st.info("No events yet.")
    else:
        # Simple table
        rows = []
        for ev in events[:30]:
            ts = ev.get('ts', 0)
            rows.append({
                "Time": datetime.fromtimestamp(ts).strftime('%H:%M:%S') if ts else "?",
                "Type": ev.get('event_type', '?'),
                "Person": ev.get('name', '') or ev.get('spg_id', '-'),
                "Camera": ev.get('_cam', ev.get('camera_id', '')),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
# Auto Refresh
# ─────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_rate)
    st.rerun()
