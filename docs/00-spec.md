# System Spec

## 1. Purpose

Sistem memonitor kehadiran SPG berdasarkan face recognition dari kamera secara real-time.
Jika SPG target tidak terlihat melebihi `presence.absent_seconds`, sistem mengirim alert Telegram dan menyimpan evidence (snapshot).
Sistem didesain untuk berjalan di edge device (PC Toko) dengan dukungan multi-kamera dan dashboard monitoring lokal.

## 2. Scope

- **Input Source**: Webcam, RTSP (CCTV), atau File Video (Simulation).
- **Multi-Camera**: Mendukung banyak kamera dalam satu outlet dengan logika kehadiran terpusat (Centralized Aggregator).
- **Dashboard**: Web interface untuk monitoring status SPG, live feed, dan event log.
- **Notification**: Alert via Telegram Bot dengan lampiran foto.
- **Resilience**: Auto-reconnect RTSP, Auto-restart worker, dan Auto-degrade performance saat beban tinggi.

## 3. Architecture Overview

Sistem menggunakan arsitektur **Multi-Process** dengan **Shared Memory** untuk performa tinggi:

1.  **Main Process (Supervisor)**: Mengelola lifecycle, konfigurasi, dan agregasi data.
2.  **Camera Workers**: Proses ringan per-kamera untuk decoding video (RTSP/Webcam) dan pre-processing.
3.  **Inference Server**: Proses tunggal yang memuat model AI (ONNX Runtime) dan Gallery wajah.
4.  **Dashboard Server**: FastAPI server untuk menyajikan UI dan API.

## 4. Key Configurations

### Recognition
- **Model**: `buffalo_s` (Fast) atau `buffalo_l` (Accurate).
- **Det Size**: `[640, 640]` (Standard) atau `[960, 960]` (High Res).
- **Threshold**: Batas kemiripan wajah (0.3 - 0.6).

### Performance
- **Process FPS**: Target FPS pengolahan (e.g., 8 - 15 FPS).
- **Frame Skip**: Rasio frame yang dilewati AI untuk menghemat resource.
- **Shared Memory**: Zero-copy transfer antara Camera Worker dan Inference Server.

### RTSP Stability
- **Transport**: TCP (Reliable) atau UDP (Low Latency).
- **Buffering**: `nobuffer` flags untuk meminimalkan delay.
- **Reconnect**: Exponential backoff strategy.

## 5. Outputs

- **Live Dashboard**: `http://localhost:8000`
- **Events Log**: `data/cam_*/events.jsonl` (JSON Lines)
- **State Data**: `data/sim_output/outlet_state.json`
- **Health Metrics**: `data/sim_output/camera_health.json`
- **Telegram Alerts**: Pesan teks + Foto snapshot.

## 6. Presence Rules

- **PRESENT**: SPG terdeteksi di *salah satu* kamera dalam outlet.
- **ABSENT**: SPG tidak terdeteksi di *semua* kamera selama > `absent_seconds`.
- **NEVER ARRIVED**: SPG belum pernah terdeteksi sejak sistem dinyalakan hingga > `absent_seconds`.
- **Alert Logic**: Dikirim 1x saat status berubah menjadi ABSENT/NEVER ARRIVED. Reset saat SPG terlihat kembali.

## 7. Security & Deployment

- **Credentials**: RTSP URL dan Telegram Token wajib menggunakan Environment Variables (`.env`).
- **Config**: File konfigurasi terpisah untuk environment berbeda (`app.dev.yaml`, `app.prod.yaml`).
- **Data Privacy**: Snapshot hanya disimpan lokal atau dikirim ke Telegram privat.

## 8. Success Criteria

- Pipeline tetap berjalan stabil 24/7 (self-healing).
- Latency dashboard < 1 detik (low latency RTSP).
- Akurasi deteksi memadai untuk membedakan SPG (dengan model `buffalo_l`).
- Resource usage (CPU/RAM) terkendali dengan fitur `frame_skip` dan `auto_degrade`.
