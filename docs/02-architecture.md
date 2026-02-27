# Architecture

## 1. High Level

```text
Camera Workers (N) -> InferenceServer (1) -> Main Loop (Router + Aggregator) -> Storage + Notifier
                                                       |
                                                       +-> Dashboard API
```

## 2. Process Model

- `run_outlet` main process:
  - routing result
  - presence aggregation
  - alert dispatch
  - health/state dump
- `InferenceServer` child process:
  - face detection + matching
  - shared memory or queue input
- `CameraWorker` per kamera:
  - capture frame
  - kirim metadata/frame ke inference
  - simpan preview AI frame untuk dashboard
- `FastAPI dashboard` process terpisah:
  - API state/events/camera list
  - stream endpoint MJPEG
  - UI monitoring dan manage SPG

## 3. Core Components

- `RTSPReader` / `WebcamReader`
- `SharedFrameBuffer`
- `FaceDetector`
- `Matcher`
- `OutletAggregator`
- `EventStore` / `GalleryStore`
- `TelegramNotifier`

## 4. Reliability Design

- Supervisor restart:
  - inference process auto restart
  - worker kamera auto restart per camera
- Restart budget guard:
  - membatasi restart per menit untuk menghindari crash loop
- Adaptive degrade:
  - `frame_skip` dinaikkan saat `queue_lag_ms` tinggi
  - diturunkan kembali saat lag stabil rendah
- RTSP reconnect:
  - exponential backoff + jitter
  - non-blocking retry schedule

## 5. Dashboard Stream Design

- Stream browser membaca `latest_frame.jpg` (AI overlay).
- Worker menulis JPEG secara atomic (temp file + replace).
- API stream menyimpan last-good-frame fallback untuk mengurangi blink/blank.

## 6. Security Design

- Secret dan credential disimpan di `.env`.
- YAML config hanya menyimpan placeholder env.
- Pipeline fail-fast jika RTSP env belum diisi saat mode RTSP aktif.

## 7. Deployment Profiles

- `dev`: smooth demo, lebih responsif.
- `staging`: profil uji lapangan.
- `prod`: lebih efisien resource dan stabil untuk operasi jangka panjang.
