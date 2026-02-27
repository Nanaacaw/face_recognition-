# MVP Checklist

## A. Setup and Config

- [x] `environment.yml` valid dan environment bisa dibuat.
- [x] Konfigurasi dibaca dari YAML + env.
- [x] Support quick switch config via command dan Makefile.
- [x] `.env.example` tersedia tanpa secret real.

## B. Security and Secrets

- [x] RTSP URL memakai env placeholder (`${RTSP_CAM_XX_URL}`).
- [x] Guard fail-fast saat RTSP env belum diisi pada mode RTSP.
- [x] Telegram token/chat id dibaca dari env.

## C. Pipeline Core

- [x] Inference centralized untuk multi-camera.
- [x] Presence logic outlet level (ANY-of-N).
- [x] Event logging per kamera.
- [x] Alert absence anti-spam.

## D. Resilience

- [x] Supervisor restart inference process.
- [x] Supervisor restart worker per kamera.
- [x] Restart budget guard untuk mencegah crash loop.
- [x] RTSP reconnect exponential backoff + jitter.
- [x] Auto-degrade runtime (`frame_skip`) saat lag tinggi.

## E. Dashboard

- [x] Monitoring status SPG dan events.
- [x] Camera health card (status/fps/lag/inference).
- [x] AI stream MJPEG stabil (last-good-frame fallback).
- [x] Raw view dihapus dari UI demo agar lebih fokus.

## F. Enrollment

- [x] Manage SPG via dashboard.
- [x] Upload foto untuk enrollment.
- [x] Hapus SPG dari gallery.

## G. Operational Readiness

- [x] Profil default untuk demo/dev, staging, dan production.
- [x] Dokumentasi command run pipeline + dashboard sudah sinkron.
- [x] Daily report tersedia untuk tracking progres harian.
