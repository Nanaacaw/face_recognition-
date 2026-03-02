# MVP Checklist

Checklist ini merepresentasikan status implementasi sistem saat ini.

## A. Setup & Config

- [x] Load config via `--config`, `APP_CONFIG_PATH`, atau `APP_ENV`
- [x] Profile config tersedia: dev, staging, prod
- [x] Placeholder env untuk RTSP URL didukung
- [x] `.env.example` tersedia tanpa secret real

## B. Pipeline Core

- [x] Multi-camera dengan centralized inference process
- [x] Shared memory path + queue fallback path
- [x] Event `SPG_SEEN` per kamera
- [x] Aggregator outlet-level untuk status kehadiran
- [x] Presence status: PRESENT / ABSENT / NEVER_ARRIVED / NOT_SEEN_YET

## C. Reliability

- [x] Supervisor restart untuk inference process
- [x] Supervisor restart untuk worker per kamera
- [x] Restart budget guard untuk cegah crash loop
- [x] RTSP reconnect exponential backoff + jitter
- [x] Auto-degrade `frame_skip` berbasis queue lag

## D. Runtime Observability

- [x] `outlet_state.json` periodik
- [x] `camera_health.json` periodik
- [x] Event log `events.jsonl` per kamera
- [x] Runtime control file (`runtime_control.json`) untuk tuning parameter tertentu

## E. Dashboard

- [x] Halaman monitoring (`/`)
- [x] Camera health cards
- [x] MJPEG AI stream per kamera
- [x] Feed recent events
- [x] Halaman manage SPG (`/manage`)

## F. Enrollment

- [x] Enrollment via upload foto (dashboard)
- [x] Enrollment via webcam (dashboard)
- [x] Enrollment via CLI (`src.app enroll`)
- [x] Delete SPG dari gallery

## G. Notification

- [x] Telegram notifier berbasis env token/chat id
- [x] Retry + backoff untuk request Telegram
- [x] Snapshot evidence saat alert absence

## H. Security & Data Hygiene

- [x] Mask credential RTSP di log
- [x] Snapshot cleaner berdasarkan retention days
- [x] Pemisahan data runtime dan gallery via subdir config
