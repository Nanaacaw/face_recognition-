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
- **Camera Health**: satu kartu per kamera dengan metrik lengkap:
  - status (LIVE / STALE / OFFLINE)
  - source type, processed FPS, inference ms, queue lag ms
  - capture→inference ms, input queue wait ms, post-inference queue ms
  - last result age, events count
- Live camera feed (AI overlay MJPEG)


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
- `GET /api/gallery`
- `POST /api/gallery/enroll`
- `DELETE /api/gallery/{spg_id}`

## 5. Manage SPG

Halaman `/manage` mendukung:

- enroll via upload foto
- daftar gallery
- hapus SPG

## 6. Notes

- Dashboard membaca data pipeline dari `data/<sim_output_subdir>` (path `storage.data_dir` di config di-resolve ke absolut terhadap project root, sehingga dashboard dan pipeline memakai direktori yang sama).
- Pastikan dashboard dan pipeline dijalankan dengan config yang sama (mis. sama-sama `app.dev.yaml`) agar Camera Health dan state tampil benar.
- Jika pipeline belum jalan, dashboard tetap bisa terbuka tetapi data kosong/offline.
