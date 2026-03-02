# Enrollment Guidelines

Akurasi recognition sangat tergantung kualitas data enrollment.

## 1. Metode Enrollment yang Didukung

- Dashboard `/manage`
  - upload foto (1-5 gambar)
  - capture webcam (1-5 gambar)
- CLI webcam:
  - `python -m src.app enroll --spg_id <id> --name "<nama>" --samples <n>`

## 2. Rekomendasi Data Minimal

Per SPG:

- minimal 3 foto, ideal 5 foto
- variasi pose ringan (depan, serong kiri/kanan)
- pencahayaan cukup dan fokus baik

## 3. Aturan Kualitas

- wajah jelas, tidak blur
- hindari resolusi terlalu kecil
- hindari kompresi berlebih dari aplikasi chat
- hindari occlusion berat (masker hitam/kacamata gelap), kecuali memang kondisi operasional harian

## 4. Validasi Teknis yang Berlaku

Saat enroll, sistem menolak sampel jika:

- confidence deteksi terlalu rendah
- wajah terlalu kecil
- embedding tidak terbentuk

Jika semua foto gagal validasi, endpoint enrollment akan mengembalikan error.

## 5. Re-enrollment Trigger

Lakukan enrollment ulang jika:

- false-negative meningkat konsisten
- perubahan tampilan signifikan (rambut, atribut)
- perubahan lighting outlet signifikan

## 6. Data yang Disimpan

Per SPG:

- file JSON berisi embedding + metadata
- last face crop (`*_last_face.jpg`)

Lokasi:

- `<storage.data_dir>/<storage.gallery_subdir>/`

## 7. Praktik Operasional

- gunakan ID SPG konsisten (tidak ganti-ganti format)
- hindari duplikasi ID untuk orang berbeda
- jika personel resign/pindah, hapus dari gallery agar tidak ikut deteksi target
