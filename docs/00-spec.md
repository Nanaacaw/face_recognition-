# face_recog — System Spec (Webcam MVP → RTSP later)

## 1) Purpose
Sistem melakukan monitoring kehadiran SPG berdasarkan face recognition.
Jika SPG target tidak terdeteksi berada di area (ROI) lebih dari 5 menit,
maka sistem mengirim alert ke Telegram disertai bukti (snapshot) dan event log.

Scope awal: Webcam (Windows).
Scope berikutnya: RTSP CCTV store (swap input source tanpa ubah core logic).

---

## 2) Definitions
### 2.1 Key terms
- **Face detection**: mendeteksi lokasi wajah pada frame.
- **Face recognition**: menentukan identitas wajah (match ke SPG gallery).
- **Embedding**: vektor representasi wajah hasil model (InsightFace).
- **Gallery**: kumpulan embedding milik SPG yang sudah di-enroll.
- **ROI (Zone)**: area frame yang dianggap “area kerja SPG”.
- **Hit**: 1 hasil recognition yang memenuhi syarat (threshold + ROI).
- **Presence**: status hadir berdasarkan hit terakhir.
- **Absence**: status tidak hadir melewati batas waktu (5 menit).

---

## 3) Inputs
### 3.1 Video source
- `webcam_index` (MVP)
- (later) `rtsp_url_main` / `rtsp_url_sub`

### 3.2 SPG gallery data
- `spg_id` (string)
- `name` (string)
- `embeddings[]` (list of vectors)
- metadata kualitas sampel (optional)

---

## 4) Outputs
### 4.1 Events (append-only)
Event ditulis ke `data/events.jsonl` sebagai JSON per baris.

Event minimal fields:
- `ts` (ISO8601)
- `env` (dev/staging/prod)
- `outlet_id`
- `camera_id`
- `event_type` (enum)
- `spg_id` (optional)
- `name` (optional)
- `similarity` (optional)
- `details` (object)
- `snapshot_path` (optional)
- `face_crop_path` (optional)

### 4.2 Telegram alert
Saat `ABSENT_ALERT_FIRED`, kirim pesan Telegram:
- SPG siapa
- durasi tidak terlihat (menit)
- outlet_id / camera_id
- lampirkan snapshot (jika ada)

---

## 5) Event Types
Enum:
- `SYSTEM_START`
- `CAMERA_ONLINE`
- `CAMERA_OFFLINE`
- `GALLERY_LOADED`
- `SPG_SEEN`               (hit valid)
- `SPG_UNKNOWN_SEEN`       (wajah ada tapi tidak match)
- `SPG_PRESENT`            (state berubah ABSENT -> PRESENT)
- `SPG_ABSENT`             (state berubah PRESENT -> ABSENT, belum alert)
- `ABSENT_ALERT_FIRED`     (alert telegram terkirim)
- `ABSENT_ALERT_FAILED`    (telegram gagal)
- `ERROR`                  (exception yang perlu dicatat)

---

## 6) Recognition Rules (Webcam MVP)
### 6.1 Processing cadence
- Capture bisa 30 fps, namun processing recognition dipatok `process_fps` (contoh 5 fps).
- Jika pipeline lambat, frame boleh drop (lebih baik drop daripada backlog).

### 6.2 Valid hit criteria (SPG_SEEN)
Agar sebuah pengenalan dianggap valid (Hit), harus memenuhi:
1) Face berada dalam ROI (default: full frame pada MVP).
2) Similarity >= `recognition.threshold`
3) Untuk mengurangi noise: perlu `recognition.min_consecutive_hits`
   (misal 2 hit dalam rentang pendek) sebelum diakui sebagai `SPG_SEEN`.

Catatan:
- Jika multiple wajah: pilih yang match paling tinggi untuk SPG target.
- Unknown face dicatat sebagai `SPG_UNKNOWN_SEEN` (optional pada MVP).

---

## 7) Presence / Absence State Machine
State per SPG (target):
- `UNKNOWN` (awal sebelum pernah terlihat)
- `PRESENT`
- `ABSENT`

Variables:
- `last_seen_ts`: timestamp hit terakhir
- `grace_seconds`: toleransi hilang sebentar (occlusion)
- `absent_seconds`: 300 detik (5 menit)
- `alert_active`: boolean (anti spam)

Rules:
1) On valid hit (`SPG_SEEN`):
   - update `last_seen_ts = now`
   - jika state != PRESENT:
     - state -> PRESENT, emit `SPG_PRESENT`
   - reset `alert_active = false`

2) Presence evaluation loop:
   - If `now - last_seen_ts <= grace_seconds`:
       state = PRESENT
   - Else:
       state = ABSENT (emit `SPG_ABSENT` hanya saat transisi)

3) Alert rule:
   - If state == ABSENT AND `now - last_seen_ts > absent_seconds` AND `alert_active == false`:
       emit `ABSENT_ALERT_FIRED` + kirim Telegram + simpan snapshot
       set `alert_active = true`
   - Jika Telegram gagal:
       emit `ABSENT_ALERT_FAILED` (tetap `alert_active=true` untuk anti spam,
       retry policy ditentukan terpisah)

Anti-spam:
- Alert hanya 1x per periode ABSENT.
- Alert baru boleh terjadi lagi setelah SPG kembali PRESENT (hit valid).

---
### 7.1 Multi-Camera Presence (Outlet Level)
Pada sistem multi-kamera:
- Presence tidak lagi dihitung per kamera.
- Presence dihitung di level outlet.

Definitions:
- last_seen_cam_i: timestamp terakhir SPG terlihat di kamera i
- last_seen_global: maksimum dari seluruh kamera
Alert hanya boleh dipicu berdasarkan last_seen_global.
Worker kamera tidak boleh mengirim alert.

## 8) Evidence (Snapshot Policy)
Pada `ABSENT_ALERT_FIRED`:
- simpan 1 snapshot full frame (`data/snapshots/<ts>_absent.jpg`)
- jika ada face crop terakhir valid, simpan juga (`..._last_s
