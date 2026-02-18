# Dashboard Monitoring

Dashboard realtime untuk monitoring kehadiran SPG di outlet.

## Quick Start

```bash
# Terminal 1: Jalankan simulasi
make simulate-light

# Terminal 2: Buka dashboard
make dashboard
```

Dashboard akan terbuka otomatis di browser pada `http://localhost:8501`.

## Fitur

### 1. Header & System Status

- Nama outlet (uppercase)
- Status **LIVE** / **OFFLINE** (berdasarkan freshness data)
- Last update timestamp

### 2. Metrics Overview

| Metric              | Deskripsi                                                  |
| ------------------- | ---------------------------------------------------------- |
| **Total Personnel** | Jumlah SPG terdaftar di config                             |
| **Present**         | SPG yang terdeteksi aktif                                  |
| **Absent**          | SPG yang hilang (termasuk Never Arrived)                   |
| **Attendance Rate** | Persentase kehadiran (hijau ≥80%, kuning ≥50%, merah <50%) |

### 3. Personnel Status Cards

Kartu untuk setiap SPG menampilkan:

- **Nama & ID**
- **Status Badge** dengan warna:
  - 🟢 PRESENT — Aktif terdeteksi
  - 🔴 ABSENT — Hilang setelah sebelumnya hadir
  - 🟠 NEVER ARRIVED — Tidak pernah terdeteksi sejak startup
  - ⚪ WAITING — Masih dalam grace period
- **Timer** — Durasi sejak terakhir terlihat
- **Foto Snapshot** — Foto terakhir yang diambil oleh kamera

> Kartu diurutkan berdasarkan prioritas: Absent → Never Arrived → Waiting → Present

### 4. Event Log

Tabel event realtime dari semua kamera:

- Filter berdasarkan **Event Type** atau **Personnel ID**
- Menampilkan: Waktu, Tipe Event, Nama SPG, Kamera

### 5. Sidebar Settings

- **Data Directory** — Folder data simulasi
- **Refresh Rate** — Interval refresh (1–10 detik)
- **Auto Refresh** — Toggle on/off
- **Show Event Log** — Tampilkan/sembunyikan event log
- **Max Events** — Batasi jumlah event yang dimuat

## Arsitektur

```
run_outlet.py  ──→  outlet_state.json  ←──  app.py (Streamlit)
    │                                            │
    ├── cam_01/events.jsonl  ──────────────────→ │ (Event Log)
    ├── cam_02/events.jsonl  ──────────────────→ │
    └── cam_*/snapshots/latest_XXX.jpg  ───────→ │ (Photos)
```

**run_outlet.py** menulis `outlet_state.json` setiap 100ms.
**app.py** membaca file ini setiap N detik (configurable).

## Konfigurasi

Target SPG dan parameter lainnya dikonfigurasi di `configs/app.dev.yaml`:

```yaml
target:
  spg_ids: ["001", "002", "003", "004", "005", "006", "007"]
  outlet_id: "OUTLET_DEV"
```
