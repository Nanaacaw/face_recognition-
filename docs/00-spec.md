# System Spec

## 1. Tujuan

Memonitor kehadiran SPG secara realtime berbasis face recognition pada level outlet (multi-kamera), dan mengirim notifikasi ketika SPG tidak terlihat melewati ambang waktu.

## 2. Ruang Lingkup

- Input video: RTSP, webcam, atau file video simulasi
- Multi-camera outlet dengan **centralized inference**
- Dashboard lokal untuk status SPG, event, health, dan live feed
- Enrollment SPG via dashboard (`/manage`) atau CLI
- Notifikasi Telegram untuk kondisi absence
- Self-healing untuk worker/inference process

## 3. Mode Operasi

### Multi-camera outlet (utama)

- Command: `python -m src.commands.run_outlet --config <yaml>`
- Entry dari Makefile: `run-demo`, `run-staging`, `run-prod`

### Single-camera (tooling)

- Command: `python -m src.app run` (webcam/rtsp single stream)
- Umumnya dipakai untuk debug cepat, bukan mode produksi outlet

### Dashboard

- Command: `python -m src.commands.run_dashboard --config <yaml>`
- UI:
  - `/` monitoring
  - `/manage` enrollment dan manajemen gallery

## 4. Arsitektur Runtime

1. Camera worker per kamera membaca frame.
2. Worker menulis frame ke shared memory (atau queue fallback) + metadata.
3. Inference server tunggal menjalankan detector + matcher.
4. Main loop:
   - routing result ke worker (overlay)
   - aggregate event outlet
   - evaluasi absence
   - tulis `outlet_state.json` + `camera_health.json`
   - kirim alert Telegram jika perlu

## 5. Aturan Presence

- `PRESENT`: SPG terdeteksi pada salah satu kamera.
- `ABSENT`: SPG pernah terlihat tetapi tidak terdeteksi lagi > `presence.absent_seconds`.
- `NEVER_ARRIVED`: SPG belum pernah terdeteksi sejak startup hingga melewati `presence.absent_seconds`.
- Alert `ABSENT_ALERT_FIRED` dikirim 1x per periode absence, reset saat SPG terlihat kembali.

## 6. Output Sistem

Basis `storage.data_dir`:

- `<sim_output_subdir>/outlet_state.json`
- `<sim_output_subdir>/camera_health.json`
- `<sim_output_subdir>/cam_XX/events.jsonl`
- `<sim_output_subdir>/cam_XX/snapshots/latest_frame.jpg`
- `<gallery_subdir>/*.json` + `*_last_face.jpg`
- `snapshots/*.jpg` (snapshot alert)

## 7. Runtime Control

File opsional:

- `<data_dir>/<sim_output_subdir>/runtime_control.json`

Field support:

- `frame_skip`
- `min_consecutive_hits`
- `min_det_score`
- `min_face_width_px`
- `auto_degrade_enabled`

## 8. Security

- RTSP URL dan Telegram credential dari environment (`.env`)
- Config YAML boleh berisi placeholder `${ENV_VAR}`
- Pipeline fail-fast jika mode RTSP aktif tapi env URL belum terisi

## 9. Kriteria Operasional

- Pipeline stabil berjalan panjang (self-healing aktif)
- Dashboard menampilkan state/health near-realtime
- Alert absence tidak spam
- Resource terkendali via `frame_skip` + auto-degrade
