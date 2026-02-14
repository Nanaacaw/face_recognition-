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

## 4) Dependency Rules

Allowed dependency direction:

FrameSource → Detector → Embedder → Matcher → Presence → EventDispatcher → Storage / Notifier

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

- Multi-camera support
- Liveness detection
- Database backend
- Web dashboard
- Metrics (Prometheus)
- GPU acceleration

Architecture must allow these without rewrite.
