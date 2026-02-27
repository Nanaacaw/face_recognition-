# Dashboard Monitoring

Dashboard digunakan untuk monitoring realtime dan manajemen SPG.

## 1. Run

Demo:

```bash
make dashboard-demo
```

Staging:

```bash
make dashboard-staging
```

Production:

```bash
make dashboard-prod
```

Default URL: `http://localhost:8000`

## 2. Main Features

- Outlet status (`LIVE` / `OFFLINE`)
- Personnel cards (`PRESENT`, `ABSENT`, `NEVER_ARRIVED`, `NOT_SEEN_YET`)
- Recent events feed
- Camera health cards:
  - status
  - processed fps
  - inference ms
  - queue lag ms
  - capture -> inference ms
  - input queue wait ms
  - post-inference queue ms
  - age
- Live camera feed (AI overlay MJPEG)
- Pipeline control:
  - start/stop `run_outlet` dari dashboard
  - runtime tuning tanpa edit YAML (via runtime control file)

## 3. Stream Behavior

- UI menampilkan AI view saja (raw view dihapus untuk fokus demo).
- Endpoint stream:
  - `/stream/{cam_id}`
  - `/stream_raw/{cam_id}` (masih tersedia backend, tidak ditampilkan di UI utama)
- Stream stabilisasi:
  - preview writer atomic file replace
  - last-good-frame fallback di API
  - response header no-cache

## 4. API Endpoints

- `GET /api/state`
- `GET /api/events`
- `GET /api/health`
- `GET /api/cameras`
- `GET /api/snapshot/{spg_id}`
- `GET /api/pipeline/status`
- `POST /api/pipeline/start`
- `POST /api/pipeline/stop`
- `GET /api/runtime/control`
- `POST /api/runtime/control`
- `GET /api/gallery`
- `POST /api/gallery/enroll`
- `DELETE /api/gallery/{spg_id}`

## 5. Manage SPG

Halaman `/manage` mendukung:

- enroll via upload foto
- daftar gallery
- hapus SPG

## 6. Notes

- Dashboard membaca data pipeline dari `data/<sim_output_subdir>`.
- Jika pipeline belum jalan, dashboard tetap bisa terbuka tetapi data kosong/offline.
- Runtime control disimpan di `data/<sim_output_subdir>/runtime_control.json`.
