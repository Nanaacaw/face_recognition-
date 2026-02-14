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
- [ ] Bisa enroll SPG:
      `spg_id`, `name`
- [ ] Gallery tersimpan di `data/gallery/`
- [ ] Enrollment punya quality gate minimal:
      - skip frame blur parah
      - minimal N samples tersimpan

## E) Recognition Realtime
- [ ] Bisa recognize SPG ter-enroll
- [ ] Unknown jika di bawah threshold
- [ ] Preview menampilkan `name + similarity`

## F) Presence Logic (Core)
- [ ] `grace_seconds` diterapkan (tidak langsung ABSENT)
- [ ] `absent_seconds` = 300 detik
- [ ] Anti-spam: alert hanya 1x sampai SPG terlihat lagi
- [ ] Event transisi tercatat:
      `SPG_PRESENT`, `SPG_ABSENT`

## G) Logging & Evidence
- [ ] `data/events.jsonl` terisi event JSONL
- [ ] Saat alert fired:
      - snapshot full frame tersimpan
      - path tercatat di event

## H) Telegram Alert
- [ ] `TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID` dibaca dari env
- [ ] Alert `ABSENT_ALERT_FIRED` masuk Telegram
- [ ] Snapshot terkirim sebagai foto (kalau enabled)

## I) Definition of Done (MVP)
MVP dianggap selesai jika:
- [ ] Enroll 1 SPG → recognize realtime
- [ ] SPG menghilang > 5 menit → Telegram alert + snapshot + event log
- [ ] SPG muncul lagi → status reset, alert bisa terjadi lagi pada periode hilang berikutnya
