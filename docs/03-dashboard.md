# Dashboard Monitoring

Dashboard adalah proses terpisah yang membaca artifact runtime dari pipeline.

## 1. Menjalankan Dashboard

```bash
make dashboard-demo
make dashboard-staging
make dashboard-prod
```

Atau:

```bash
python -m src.commands.run_dashboard --config configs/app.dev.yaml
```

Default URL: `http://localhost:8000`

## 2. Halaman

- `/`: monitoring outlet realtime
- `/manage`: enrollment + manajemen SPG

## 3. Fitur Halaman Monitoring (`/`)

- status sistem (`LIVE` / `OFFLINE`)
- statistik personnel (total/present/absent/rate)
- kartu status SPG (PRESENT/ABSENT/NEVER_ARRIVED/NOT_SEEN_YET)
- feed event terbaru
- camera health cards:
  - status kamera (`LIVE`, `STALE`, `OFFLINE`)
  - processed FPS
  - inference time, queue lag
  - capture->inference, queue wait, post-inference queue
  - last result age, events count
- live stream MJPEG per kamera (`latest_frame.jpg`)

## 4. Fitur Halaman Manage (`/manage`)

- list gallery SPG
- enroll SPG via upload (max 5 foto)
- enroll SPG via webcam browser
- hapus SPG dari gallery

## 5. API Endpoints

- `GET /api/state`
- `GET /api/events`
- `GET /api/health`
- `GET /api/cameras`
- `GET /api/snapshot/{spg_id}`
- `GET /api/gallery`
- `GET /api/gallery/{spg_id}/photo`
- `POST /api/gallery/enroll`
- `DELETE /api/gallery/{spg_id}`
- `GET /stream/{cam_id}`
- `GET /stream_raw/{cam_id}`

## 6. Data Source Dashboard

Dashboard membaca path dari config:

- data runtime:
  - `<storage.data_dir>/<storage.sim_output_subdir>`
- gallery:
  - `<storage.data_dir>/<storage.gallery_subdir>`

Pastikan pipeline dan dashboard memakai profile config yang sama.

## 7. Stream Stabilization

- preview frame ditulis worker secara atomic replace
- stream endpoint validasi boundary JPEG
- jika frame terbaru invalid/hilang, pakai last-good-frame

## 8. Catatan Operasional

- Dashboard tetap bisa start tanpa pipeline, tetapi data kosong/offline
- `stream_raw` tersedia di backend walau UI utama fokus pada AI stream
