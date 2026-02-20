# face_recognition

Sistem monitoring SPG berbasis face recognition. Jika SPG target tidak terdeteksi melewati batas waktu (default 5 menit), sistem mengirim alert ke Telegram beserta snapshot dan event log.

## Persyaratan

- Windows (scope awal)
- Conda
- Webcam atau RTSP (lihat config)

## Setup

```bash
conda env create -f environment.yml
conda activate face_recog
cp .env.example .env
```

Edit `.env` untuk `SPG_TELEGRAM_BOT_TOKEN` dan `SPG_TELEGRAM_CHAT_ID` jika ingin alert Telegram. `APP_ENV` memilih file config (`configs/app.<env>.yaml`), atau pakai `APP_CONFIG_PATH` untuk path custom.

## Command

| Perintah | Keterangan |
|----------|------------|
| `make run` | Jalankan pipeline (recognize + presence + alert) |
| `make enroll` | Enroll SPG (contoh: 001, 30 samples). Custom: `python -m src.app enroll --spg_id 002 --name "Nama" --samples 30` |
| `python -m src.app debug` | Preview webcam + face detection (bbox) |

Tanpa Make: `python -m src.app run`, `python -m src.app enroll --spg_id 001 --name "Nama" --samples 30`.

## Struktur Proyek

```
face_recog/
├── configs/
│   ├── app.dev.yaml
│   ├── app.prod.yml
│   └── app.staging.yaml
├── data/
│   ├── events.jsonl
│   └── gallery/
│       └── <spg_id>.json
├── docs/
│   ├── 00-spec.md
│   ├── 01-mvp-checklist.md
│   ├── 02-architecture.md
│   ├── 03-config-reference.md
│   └── 04-enrollment-guidelines.md
├── src/
│   ├── app.py
│   ├── commands/
│   │   └── run_webcam.py
│   ├── domain/
│   │   └── events.py
│   ├── enrollment/
│   │   └── enroll_webcam.py
│   ├── notification/
│   │   └── telegram_notifier.py
│   ├── pipeline/
│   │   ├── face_detector.py
│   │   ├── matcher.py
│   │   ├── presence_logic.py
│   │   └── webcam_reader.py
│   ├── settings/
│   │   └── settings.py
│   └── storage/
│       ├── event_store.py
│       ├── gallery_store.py
│       └── snapshot_store.py
├── .env.example
├── environment.yml
├── Makefile
└── README.md
```

## Dokumentasi

- `docs/00-spec.md` — Spesifikasi sistem
- `docs/01-mvp-checklist.md` — Checklist MVP
- `docs/02-architecture.md` — Arsitektur
- `docs/03-config-reference.md` — Referensi config
- `docs/04-enrollment-guidelines.md` — Panduan enrollment
