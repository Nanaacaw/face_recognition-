# face_recog — Architecture Design

## 1) Design Philosophy

Project ini mengikuti prinsip:

- Separation of Concerns
- Config-driven behavior
- Replaceable input source (webcam → RTSP)
- Auditability (event log + snapshot evidence)
- No hardcoded business logic

Core monitoring logic harus bisa berjalan tanpa:
- Telegram
- OpenCV window
- File system
- RTSP specifics

Semua I/O harus berada di layer terpisah.

---

## 2) High-Level Data Flow

FrameSource
    ↓
FaceDetector
    ↓
FaceEmbedder
    ↓
Matcher (Gallery compare)
    ↓
PresenceEngine (State Machine)
    ↓
Event Dispatcher
    ↙            ↘
EventStore     Notifier (Telegram)
    ↓
SnapshotStore

---

## 3) Component Responsibilities

### 3.1 FrameSource
Interface:
- `read() -> frame`

Implementations:
- WebcamReader
- RTSPReader (future)

Responsibility:
- Provide frame
- Handle reconnect (for RTSP)
- Frame throttling (via process_fps)

---

### 3.2 FaceDetector
Responsibility:
- Detect face bounding boxes
- Provide face crop + landmarks (if available)

Must NOT:
- Send Telegram
- Decide presence logic

---

### 3.3 FaceEmbedder
Responsibility:
- Convert face crop → embedding vector
- No business logic

---

### 3.4 Matcher
Responsibility:
- Compare embedding to gallery
- Return:
  - spg_id
  - similarity score
  - match / unknown

Threshold must be config-driven.

---

### 3.5 PresenceEngine
Core business logic.

Responsibilities:
- Track last_seen per SPG
- Maintain state: PRESENT / ABSENT
- Handle grace window
- Handle 5-minute absence rule
- Emit events:
  - SPG_PRESENT
  - SPG_ABSENT
  - ABSENT_ALERT_FIRED

Must NOT:
- Know about Telegram
- Know about OpenCV
- Know about file system

---

### 3.6 EventDispatcher
Responsibility:
- Broadcast event to:
  - EventStore
  - SnapshotStore
  - Notifier

Loose coupling required.

---

### 3.7 Storage Layer

#### GalleryStore
- Load SPG embeddings
- Save new enrollments

#### EventStore
- Append JSON event to file

#### SnapshotStore
- Save full frame image
- Save face crop image
- Enforce retention policy

---

### 3.8 Notifier (Telegram)

Responsibility:
- Send message
- Send photo
- Handle retry / failure
- Emit ABSENT_ALERT_FAILED if necessary

---

### 3.9 Web Dashboard & API (New)

**Frontend**:
- UI Monitoring Realtime (Alpine.js + Jinja2)
- Manage SPG (Enrollment Form)

**Backend API**:
- `GET /api/state`: Provide global aggregated state
- `POST /api/gallery/enroll`: Handle photo upload & embedding extraction
- `GET /stream/{cam_id}`: Proxy MJPEG stream

Responsibility:
- Provide user interface
- Handle enrollment (Photo -> FaceDetector -> GalleryStore)
- Read-only monitoring of system state

---

## 4) Dependency Rules

Allowed dependency direction:

FrameSource → Detector → Embedder → Matcher → Presence → EventDispatcher → Storage / Notifier
Dashboard → Storage (Read) / Detector (Enrollment)

Not allowed:
- Presence importing cv2
- Matcher importing telegram
- Detector writing files

---

## 5) Environment Separation

Config file:
- app.dev.yaml
- app.staging.yaml
- app.prod.yaml

Secrets:
- Environment variables only

Code must NOT branch like:
if ENV == "prod": do different logic

Behavior difference must come from config.

---

## 6) Future Extensions (Not in MVP)

- Multi-camera support (Done via OutletAggregator)
- Liveness detection
- Database backend (SQLite/Postgres)
- Metrics (Prometheus)
- GPU acceleration (Supported via ONNX Runtime)

Architecture must allow these without rewrite.

## 7) Multi-Camera Outlet Architecture (v2 — Centralized Inference)

### 7.1 Motivation
Dalam satu outlet dapat terdapat lebih dari satu kamera (2–6 CCTV).
SPG dianggap PRESENT jika terdeteksi pada salah satu kamera (ANY-of-N rule).

**Problem**: N worker = N model load (RAM & CPU heavy).
**Solution**: Sidecar Pattern — 1 InferenceServer + N lightweight Camera Readers.

### 7.2 Architecture Flow

```
Camera Worker A ──┐                    SharedMemory (zero-copy)
Camera Worker B ──┼──→ input_queue ──→ InferenceServer (1 model load)
Camera Worker C ──┘    (metadata)              │
                                               ▼
                                         output_queue
                                               │
                                      Main Process (Router)
                                       ├→ feedback_queues[cam_id] → Workers (visualization)
                                       └→ OutletAggregator → Events → Alerts → Telegram
```

### 7.3 Camera Worker Responsibilities

Worker (per camera) bertugas:
- Capture frame (webcam / RTSP / video file)
- Write frame to SharedMemory (zero-copy)
- Send lightweight metadata tuple to input_queue
- Receive inference results via feedback_queue → Draw bbox on frame
- Save preview thumbnail for dashboard (1x/sec)

Worker MUST NOT:
- Load ML model
- Run face detection or embedding extraction
- Fire absence alerts
- Send Telegram

### 7.4 InferenceServer Responsibilities

Single process:
- Load model ONCE (FaceDetector + Matcher)
- Read frames from SharedMemory by camera_id
- Apply frame_skip (configurable: skip N frames between inferences)
- Detect faces → Extract embeddings → Match gallery
- Send results to output_queue

### 7.5 Main Process (Router + Aggregator)

- Drain output_queue
- Dispatch results to feedback_queues (per-camera, for visualization)
- Convert matched faces to Events → EventStore
- Feed events to OutletAggregator
- Run absence tick → Fire alerts

### 7.6 SharedMemory & Frame Skip (Performance)

- SharedMemory eliminates ~24MB/s pickle overhead (4 cameras @ 5 FPS)
- frame_skip reduces inference load (e.g., frame_skip=2 → process 1 in 3 frames)
- Configurable via `inference` section in YAML:
  ```yaml
  inference:
    frame_skip: 0
    max_frame_height: 720
    max_frame_width: 1280
  ```

### 7.7 ANY-of-N Rule
SPG dianggap PRESENT jika:
`now - max(last_seen_cam_i) <= absent_seconds`

SPG dianggap ABSENT hanya jika:
- Tidak terlihat di seluruh kamera
- Melebihi absent_seconds

### 7.8 Deployment
```bash
# Terminal 1: Start pipeline (auto-spawns workers + inference server)
make run          # Production RTSP
make simulate     # Dev simulation

# Terminal 2: Start dashboard
make dashboard
```

