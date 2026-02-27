# face_recognition

Sistem monitoring kehadiran SPG berbasis face recognition.
Pipeline memproses stream kamera, menghasilkan event presence, dan mengirim alert Telegram saat SPG target tidak terlihat melebihi batas waktu.

## Prerequisites

- Windows
- Conda
- Kamera webcam atau RTSP

## Setup

```bash
conda env create -f environment.yml
conda activate face_recog
copy .env.example .env
```

Isi `.env` minimal:

- `SPG_TELEGRAM_BOT_TOKEN` (opsional jika notifikasi aktif)
- `SPG_TELEGRAM_CHAT_ID` (opsional jika notifikasi aktif)
- `RTSP_CAM_01_URL`
- `RTSP_CAM_02_URL`
- `RTSP_CAM_03_URL`
- `RTSP_CAM_04_URL`

Config resolution:

1. `APP_CONFIG_PATH` (jika diisi)
2. `APP_ENV` -> `configs/app.<env>.yaml`
3. default `dev`

## Quick Run

Jalankan pipeline dan dashboard di terminal terpisah.

Demo:

```bash
make run-demo
make dashboard-demo
```

Staging:

```bash
make run-staging
make dashboard-staging
```

Production:

```bash
make run-prod
make dashboard-prod
```

Dashboard default: `http://localhost:8000`

## Main Commands

| Command | Description |
|---|---|
| `make run` | Run multi-camera pipeline with current env config |
| `make run-demo` | Run pipeline with `configs/app.dev.yaml` |
| `make run-staging` | Run pipeline with `configs/app.staging.yaml` |
| `make run-prod` | Run pipeline with `configs/app.prod.yaml` |
| `make simulate` | Simulation mode with preview window |
| `make simulate-light` | Simulation mode without preview window |
| `make dashboard` | Run dashboard with current env config |
| `make dashboard-demo` | Run dashboard with `configs/app.dev.yaml` |
| `make dashboard-staging` | Run dashboard with `configs/app.staging.yaml` |
| `make dashboard-prod` | Run dashboard with `configs/app.prod.yaml` |
| `make enroll` | Enroll sample SPG via CLI |
| `make debug` | Preview + face detection debug |

## Security Notes

- Jangan hardcode RTSP credential di file YAML.
- Gunakan placeholder env di config, contoh: `${RTSP_CAM_01_URL}`.
- Jangan commit `.env` ke repository.
- Jika credential pernah terlanjur ter-push, lakukan rotate credential kamera.

## Key Runtime Features

- Centralized inference (1 model process untuk banyak kamera)
- Worker supervisor restart (self-healing per process)
- Adaptive auto-degrade (`frame_skip` naik turun otomatis saat lag tinggi)
- RTSP reconnect exponential backoff + jitter
- Dashboard MJPEG AI view dengan fallback frame terakhir agar lebih stabil

## Documentation

- `docs/00-spec.md`
- `docs/01-mvp-checklist.md`
- `docs/02-architecture.md`
- `docs/03-config-reference.md`
- `docs/03-dashboard.md`
- `docs/04-enrollment-guidelines.md`
- `docs/05-system-flow.md`
