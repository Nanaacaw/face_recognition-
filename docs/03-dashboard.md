# Dashboard Monitoring

Dashboard realtime untuk monitoring kehadiran SPG di outlet.

## Quick Start

```bash
# Terminal 1: Jalankan simulasi (Opsional, jika ingin data dummy)
make simulate-light

# Terminal 2: Buka dashboard
python -m src.frontend.main
```

Dashboard akan terbuka otomatis di browser pada `http://localhost:8000`.

## Fitur

### 1. Monitoring (Realtime)
Halaman utama (`/`) menampilkan status kehadiran SPG.

- **Status Badge**:
  - 🟢 PRESENT — Aktif terdeteksi
  - 🔴 ABSENT — Hilang setelah sebelumnya hadir
  - 🟠 NEVER ARRIVED — Tidak pernah terdeteksi sejak startup
  - ⚪ WAITING — Masih dalam grace period
- **Event Log**: Tabel log aktivitas terbaru dari semua kamera.
- **Camera Stream**: Klik "Show Cameras" untuk melihat feed MJPEG (jika tersedia).

### 2. Manage SPG (Enrollment)
Halaman baru (`/manage`) untuk mendaftarkan wajah SPG.

**Cara Enroll:**
1.  Klik menu **"👥 Manage SPG"** di pojok kanan atas.
2.  Isi **SPG ID** dan **Nama**.
3.  Pilih Metode:
    - **📁 Upload Foto**: Drag & drop 1-5 file foto wajah.
    - **📹 Webcam**: Gunakan kamera laptop/PC untuk capture wajah langsung.
4.  Klik **"Daftarkan SPG"**.

> **Note:**
> - Pastikan pencahayaan cukup terang.
> - Wajah harus menghadap kamera.
> - Sistem otomatis mendeteksi wajah terbaik dari foto yang diupload.

**Hapus SPG:**
Klik tombol **🗑️ Hapus** pada tabel daftar SPG untuk menghapus data permanent (json + foto).

## Arsitektur

```
[Browser] <──> [FastAPI (main.py)] <──> [GalleryStore]
                        │
                        ▼
                 [FaceDetector] (Singleton)
```

- **Backend**: FastAPI
- **Frontend**: Jinja2 Templates + Alpine.js + Tailwind CSS
- **Storage**: JSON-based (`data/gallery/*.json`)

## Konfigurasi

Semua parameter (Model, Threshold, Camera) diatur di `configs/app.dev.yaml`.

```yaml
recognition:
  model_name: "buffalo_l"       # Model deteksi (buffalo_s / buffalo_l)
  det_size: [640, 640]          # Ukuran input deteksi
  execution_providers:
  - "CUDAExecutionProvider"     # Prioritas GPU
  - "CPUExecutionProvider"
```
