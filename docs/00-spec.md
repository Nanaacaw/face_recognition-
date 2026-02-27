# System Spec

## 1. Purpose

Sistem memonitor kehadiran SPG berdasarkan face recognition dari kamera.
Jika SPG target tidak terlihat melebihi `presence.absent_seconds`, sistem mengirim alert Telegram dan menyimpan evidence.

## 2. Scope

- Input source: webcam, RTSP, atau file video (simulation).
- Multi-camera outlet dengan aturan presence level outlet (ANY-of-N).
- Dashboard realtime untuk status, event, health kamera, dan stream AI view.

## 3. Inputs

- Kamera:
  - `camera.source=webcam` + `camera.webcam_index`
  - `camera.source=rtsp` + `camera.rtsp_url`
  - `outlet.cameras[].rtsp_url` untuk mode multi-camera
- Gallery SPG: JSON embedding + photo di `data/gallery`.
- Runtime config dari YAML + env variables.

## 4. Outputs

- Event JSONL per kamera (`events.jsonl`).
- State outlet (`outlet_state.json`).
- Health telemetry (`camera_health.json`).
- Snapshot preview stream (`latest_frame.jpg`).
- Alert Telegram (opsional jika enabled).

## 5. Presence Rules

- SPG dianggap `PRESENT` jika ada hit valid dari salah satu kamera.
- SPG dianggap `ABSENT` jika tidak ada hit valid lebih lama dari `presence.absent_seconds`.
- Alert absence anti-spam: satu kali per periode absence, reset saat SPG terlihat lagi.

## 6. Reliability Requirements

- Worker kamera dan inference process harus self-healing (auto restart).
- RTSP reconnect memakai backoff + jitter saat jaringan/kamera bermasalah.
- Saat overload, sistem boleh degrade otomatis via `frame_skip` untuk menjaga pipeline tetap hidup.
- Dashboard stream harus tetap stabil saat ada transient file read/write error.

## 7. Security Requirements

- RTSP credential wajib lewat env var, bukan hardcoded.
- Contoh placeholder di config: `${RTSP_CAM_01_URL}`.
- Secret Telegram tetap di `.env`.

## 8. Non-Goals

- Tidak menargetkan true live ultra-low latency (WebRTC) di versi ini.
- Tidak menyimpan video full recording sebagai fitur utama.

## 9. Success Criteria

- Pipeline tetap berjalan walau satu kamera drop.
- Inference process bisa restart otomatis jika crash.
- Dashboard tetap menampilkan stream AI tanpa blank berkepanjangan.
- Alert absence terkirim konsisten saat kondisi terpenuhi.
