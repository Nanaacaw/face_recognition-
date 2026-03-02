# Architecture

## 1. High-Level Topology

```text
Camera Workers (N)
  -> input_queue (+ shared memory buffers per camera)
  -> Inference Server (1)
  -> output_queue
  -> Main Loop (Aggregator + Supervisor + Notifier)
  -> JSON/JPEG artifacts
  -> Dashboard API/UI
```

## 2. Process Model

### `run_outlet` (main process)

- load config
- spawn inference process
- spawn worker process per kamera
- jalankan loop:
  - supervise restart
  - aggregate events
  - evaluate absence
  - emit health/state JSON

### Camera worker process (`worker_camera_capture`)

- read frame dari RTSP/webcam/file
- throttle by `camera.process_fps`
- kirim metadata + frame pointer (shared memory) ke inference
- terima feedback inference untuk overlay
- simpan preview frame untuk dashboard

### Inference server process (`InferenceServer`)

- load model detector 1x
- load gallery embeddings 1x
- infer frame dari semua kamera
- apply runtime gate:
  - `frame_skip`
  - `min_det_score`
  - `min_face_width_px`
  - ROI per kamera

### Dashboard process (`run_dashboard` / `src.frontend.main`)

- baca file output pipeline
- expose API + MJPEG stream
- serve halaman monitoring dan manage SPG

## 3. Komponen Utama

- `src/commands/run_outlet.py`
- `src/pipeline/inference_server.py`
- `src/pipeline/outlet_aggregator.py`
- `src/pipeline/rtsp_reader.py`
- `src/pipeline/shared_frame_buffer.py`
- `src/frontend/main.py`
- `src/storage/*`

## 4. Resilience Design

- Restart cooldown dan restart budget per menit
- Worker restart dilakukan per kamera (isolated failure)
- Inference restart terpisah dari worker
- RTSP reconnect pakai exponential backoff + jitter
- Auto-degrade menyesuaikan `frame_skip` berdasarkan lag

## 5. Data Contract (Pipeline -> Dashboard)

- `outlet_state.json`: status SPG per outlet
- `camera_health.json`: metrik kesehatan kamera + supervisor
- `cam_XX/events.jsonl`: event timeline
- `cam_XX/snapshots/latest_frame.jpg`: stream frame AI overlay

## 6. Runtime Tuning Contract

Pipeline membaca `runtime_control.json` untuk update parameter runtime tanpa restart (subset parameter).

## 7. Separation of Concerns

- Reader: akuisisi frame + reconnect
- Inference: detect + match
- Aggregator: domain presence outlet
- Storage: persist event/snapshot/gallery
- Frontend API: read model untuk UI, bukan compute model
