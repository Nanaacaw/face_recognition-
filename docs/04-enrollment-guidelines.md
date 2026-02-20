# face_recog — Enrollment Guidelines

## 1) Purpose

Enrollment quality determines recognition accuracy.
Bad enrollment = high false negative or false positive.

---

## 2) Minimum Requirements

For each SPG:

- Capture 20–50 good-quality samples
- Face size ≥ 100px width (recommended)
- Clear focus (no motion blur)
- Lighting adequate (not overexposed)
- Avoid extreme angles

---

## 3) Enrollment Process

### 3.1 Web Dashboard (Recommended)
Gunakan halaman `/manage` pada dashboard.

1. **Upload Foto**:
   - Cocok jika SPG tidak ada di lokasi.
   - Upload 3–5 foto wajah berbeda (depan, serong kiri, serong kanan).
   - Sistem otomatis crop wajah terbaik.

2. **Webcam Capture**:
   - Cocok jika SPG ada di depan PC admin.
   - Klik "Capture" 3–5 kali sambil minta SPG sedikit mengubah pose.

### 3.2 CLI Command (Legacy/Dev Only)
Hanya gunakan jika tidak bisa akses dashboard.
`python -m src.enrollment.enroll_webcam ...`

---

## 4) Pose Variation

Include:
- Slight left/right turn
- Slight up/down tilt
- Neutral expression

Avoid:
- Extreme profile
- Face covered
- Sunglasses
- Mask (unless system must support mask)

---

## 5) Do NOT

- Enroll from random selfie with different camera angle
- Use compressed WhatsApp image
- Use only 1 single image
- Enroll from CCTV far-distance face

---

## 6) Re-enrollment Policy

Re-enroll SPG if:
- Hairstyle drastically changes
- Recognition drops significantly
- Mask policy changes
- Lighting environment changes

---

## 7) Gallery Storage Policy

For each SPG:
- Store:
  - spg_id
  - name
  - list of embeddings
  - enrollment timestamp
- Do NOT store excessive raw face images (privacy risk)

---

## 8) Recognition Threshold Impact

Lower threshold:
- More tolerant
- Higher false positive risk

Higher threshold:
- Safer identity
- More false negative

Threshold tuning must be done in staging environment.
