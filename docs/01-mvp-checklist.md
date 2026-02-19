# face_recog — MVP Checklist (Webcam)

## A) Setup & Reproducibility
- [ ] Repo punya folder: `src/`, `configs/`, `data/`, `docs/`, `scripts/`
- [ ] `environment.yml` ada dan bisa dibuat di Windows
- [ ] `conda activate face_recog` lalu import sukses:
      `cv2`, `numpy`, `insightface`, `onnxruntime`

## B) Config & Secrets
- [ ] Ada `.env.example` (tanpa secrets real)
- [ ] Ada `configs/app.dev.yaml`
- [ ] Setting tidak hardcode (threshold/timer/fps)

## C) Webcam Pipeline
- [ ] Command debug preview webcam berjalan
- [ ] Face detection overlay terlihat (bbox)
- [ ] Processing fps sesuai config (frame drop allowed)

## D) Enrollment (Gallery)
- [x] Bisa enroll SPG:
      `spg_id`, `name`, `upload/webcam`
- [x] Gallery tersimpan di `data/gallery/` (format JSON + JPG)
- [x] Enrollment punya quality gate minimal:
      - skip frame blur parah
      - minimal N samples tersimpan

## E) Recognition Realtime
- [x] Bisa recognize SPG ter-enroll
- [x] Unknown jika di bawah threshold
- [x] Preview menampilkan `name + similarity`

## F) Presence Logic (Core)
- [x] `grace_seconds` diterapkan (tidak langsung ABSENT)
- [x] `absent_seconds` = 300 detik
- [x] Anti-spam: alert hanya 1x sampai SPG terlihat lagi
- [x] Event transisi tercatat:
      `SPG_PRESENT`, `SPG_ABSENT`

## G) Logging & Evidence
- [x] `data/events.jsonl` terisi event JSONL
- [x] Saat alert fired:
      - snapshot full frame tersimpan
      - path tercatat di event

## H) Telegram Alert
- [x] `TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID` dibaca dari env
- [x] Alert `ABSENT_ALERT_FIRED` masuk Telegram
- [x] Snapshot terkirim sebagai foto (kalau enabled)

## I) Performance & Tools
- [x] Vectorized Matcher (NumPy) untuk high-throughput
- [x] Configurable FaceDetector (`buffalo_l` / `buffalo_s`)
- [x] FastAPI Dashboard (`/manage` untuk enrollment)

## J) Definition of Done (MVP)
MVP dianggap selesai jika:
- [x] Enroll 1 SPG → recognize realtime
- [x] SPG menghilang > 5 menit → Telegram alert + snapshot + event log
- [x] SPG muncul lagi → status reset, alert bisa terjadi lagi pada periode hilang berikutnya
