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

## 3) Recommended Capture Process (Webcam MVP)

1. Ask SPG to stand in front of webcam
2. Capture frames over 5–10 seconds
3. Automatically:
   - Skip blurred frames
   - Skip very small faces
   - Skip overexposed frames
4. Store embeddings only (not raw image by default)

Optional:
- Save sample face crops for audit

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
