# face_recog — Configuration Reference

Semua konfigurasi sistem dibaca dari:

configs/app.<env>.yaml

Environment:
- dev
- staging
- prod

Secrets (Telegram) harus dibaca dari environment variables.

---

# 1) camera

## camera.source
Type: string  
Allowed: "webcam" | "rtsp"  
Description:
Menentukan sumber video.

---

## camera.webcam_index
Type: int  
Default: 0  
Used when: source = webcam  
Description:
Index device webcam pada sistem Windows.

---

## camera.rtsp_url
Type: string  
Used when: source = rtsp  
Description:
RTSP URL stream kamera.

---

## camera.process_fps
Type: int  
Recommended: 3–5  
Description:
Berapa fps diproses untuk recognition.
Frame lain boleh di-drop untuk menjaga performa.

Impact:
- Terlalu tinggi → CPU naik
- Terlalu rendah → detection delay

---

## camera.preview
Type: boolean  
Description:
Jika true, tampilkan OpenCV preview window.
Biasanya true di dev, false di prod.

---

# 2) recognition

## recognition.threshold
Type: float (0.0–1.0)  
Typical: 0.40–0.55  

Description:
Minimum similarity agar dianggap match.

Lower value:
- Lebih toleran
- Risiko false positive naik

Higher value:
- Lebih ketat
- Risiko false negative naik

Must be tuned in staging.

---

## recognition.model_name
Type: string
Default: "buffalo_s"
Allowed: "buffalo_s" | "buffalo_l"

Description:
Model deteksi wajah yang digunakan.
- `buffalo_s`: Lebih cepat (MobileFaceNet), akurasi standar.
- `buffalo_l`: Lebih akurat (ResNet50), lebih berat.

---

## recognition.det_size
Type: list[int, int]
Default: [640, 640]

Description:
Ukuran input gambar untuk deteksi wajah.
Resolusi lebih tinggi = deteksi wajah kecil lebih baik, tapi lebih lambat.

---

## recognition.execution_providers
Type: list[string]
Default: ["CUDAExecutionProvider", "CPUExecutionProvider"]

Description:
Urutan prioritas hardware acceleration (ONNX Runtime).
Jika CUDA tidak tersedia, otomatis fallback ke CPU.

---

## recognition.min_consecutive_hits
Type: int  
Recommended: 2–3  

Description:
Jumlah hit berturut-turut sebelum dianggap valid SPG_SEEN.

Purpose:
Mengurangi noise dan false detection satu frame.

---

# 3) presence

## presence.grace_seconds
Type: int  
Recommended: 15–30  

Description:
Toleransi waktu hilang sementara (misalnya tertutup orang).

Jika SPG tidak terlihat kurang dari waktu ini,
status tetap dianggap PRESENT.

---

## presence.absent_seconds
Type: int  
Default: 300 (5 menit)  

Description:
Batas waktu tidak terlihat sebelum alert dikirim.

If:
now - last_seen > absent_seconds
→ ABSENT_ALERT_FIRED

---

# 4) storage

## storage.data_dir
Type: string  
Default: "./data"  

Description:
Root folder untuk:
- gallery
- snapshots
- events.jsonl

---

## storage.snapshot_enabled
Type: boolean  
Description:
Jika true, sistem menyimpan snapshot saat alert.

---

## storage.snapshot_retention_days
Type: int  
Recommended:
- dev: 3–7
- prod: 7–30

Description:
Berapa hari snapshot disimpan sebelum dihapus.

---

# 5) target

## target.spg_ids
Type: list[string]  

Description:
Daftar SPG yang dimonitor.

MVP:
Biasanya hanya 1 SPG per kamera.

Future:
Bisa multi-SPG.

---

## target.outlet_id
Type: string  
Description:
Identifier outlet.

Dicatat di event log dan Telegram.

---

## target.camera_id
Type: string  
Description:
Identifier kamera.

Dicatat di event log dan Telegram.

---

# 6) Environment Variables (Secrets)

Must exist in system environment:

- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- APP_ENV (dev/staging/prod)

These must NEVER be committed to Git.

---

# 7) Config Philosophy

Rules:
- Semua parameter yang mungkin berubah harus ada di config.
- Tidak boleh hardcode threshold di source code.
- Tidak boleh conditional logic berdasarkan ENV di kode.
- Perbedaan behavior harus berasal dari config file.
- RTSP credentials TIDAK boleh di-commit ke Git.
  - `configs/app.dev.yaml` → gitignored.
  - `configs/app.dev.yaml.example` → committed (template tanpa credential).

---

# 8) inference (Centralized Mode)

## inference.frame_skip
Type: int
Default: 0

Description:
Jumlah frame yang dilewati antara setiap inference.
- `0` = proses setiap frame (no skip)
- `2` = proses 1 dari 3 frame

Berguna pada hardware lemah dengan banyak kamera.

---

## inference.max_frame_height
Type: int
Default: 720

Description:
Tinggi maksimum frame yang di-buffer di SharedMemory.
Frame yang lebih tinggi akan di-resize otomatis sebelum dikirim ke InferenceServer.
**Tidak mempengaruhi akurasi** — model InsightFace selalu resize ke `det_size` secara internal.

---

## inference.max_frame_width
Type: int
Default: 1280

Description:
Lebar maksimum frame yang di-buffer di SharedMemory.
Bersama `max_frame_height`, menentukan total alokasi RAM per kamera:
`max_frame_height × max_frame_width × 3 bytes` (~2.6MB untuk 720p).

---

# 9) Tuning Strategy

Tuning order:

1. Adjust recognition.threshold
2. Adjust min_consecutive_hits
3. Adjust grace_seconds
4. Adjust process_fps
5. Adjust inference.frame_skip (jika CPU/GPU overload)

Never tune everything at once.

---

# 10) Deployment

## Centralized Mode (Production)

Semua kamera dalam satu outlet dikelola oleh **1 command**:

```bash
# Terminal 1: Pipeline (auto-spawn semua workers + inference server)
make run           # Production (RTSP cameras)
make simulate      # Dev (video files)

# Terminal 2: Dashboard
make dashboard
```

**Proses yang berjalan**: 1 main + 1 inference + N cameras + 1 dashboard = N + 3.

## Konfigurasi per Outlet

Setiap outlet menggunakan 1 config file:
```
configs/app.dev.yaml       → Development
configs/app.staging.yaml   → Staging
configs/app.prod.yaml      → Production
```

Dipilih melalui `APP_ENV` di `.env`:
```
APP_ENV=dev       → configs/app.dev.yaml
APP_ENV=prod      → configs/app.prod.yaml
```