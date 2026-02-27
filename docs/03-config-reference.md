# Configuration Reference

Semua runtime behavior dibaca dari YAML config + env variables.

## 1. Config Resolution

Urutan prioritas:

1. `APP_CONFIG_PATH`
2. `APP_ENV` -> `configs/app.<env>.yaml`
3. default `dev`

## 2. camera

### `camera.source`

- Type: `string`
- Allowed: `webcam | rtsp`

### `camera.webcam_index`

- Type: `int | null`
- Dipakai saat `camera.source=webcam`

### `camera.rtsp_url`

- Type: `string | null`
- Dipakai saat `camera.source=rtsp`
- Rekomendasi: `${RTSP_CAM_01_URL}`

### `camera.process_fps`

- Type: `int`
- Fungsi: membatasi rate frame yang diproses pipeline

### `camera.preview`

- Type: `bool`
- Menyalakan preview OpenCV window

## 3. recognition

### `recognition.threshold`

- Type: `float`

### `recognition.min_consecutive_hits`

- Type: `int`
- Fungsi: minimum streak frame match sebelum event `SPG_SEEN` diterima.

### `recognition.min_det_score`

- Type: `float`
- Fungsi: confidence minimum dari detector sebelum face diproses ke matching.

### `recognition.min_face_width_px`

- Type: `int`
- Fungsi: minimum lebar wajah (pixel) agar face kecil/noisy tidak ikut matching.

### `recognition.model_name`

- Type: `string`
- Default: `buffalo_s`

### `recognition.execution_providers`

- Type: `list[string]`
- Contoh: `["CUDAExecutionProvider", "CPUExecutionProvider"]`

### `recognition.det_size`

- Type: `list[int, int]` atau `tuple[int, int]`

## 4. presence

### `presence.grace_seconds`

- Type: `int`

### `presence.absent_seconds`

- Type: `int`

## 5. storage

### `storage.data_dir`

- Type: `string`

### `storage.snapshot_enabled`

- Type: `bool`

### `storage.snapshot_retention_days`

- Type: `int`

### `storage.sim_output_subdir`

- Type: `string`
- Default: `sim_output`

### `storage.gallery_subdir`

- Type: `string`
- Default: `gallery`

## 6. target (single-camera mode)

### `target.spg_ids`

- Type: `list[string]`

### `target.outlet_id`

- Type: `string`

### `target.camera_id`

- Type: `string`

## 7. outlet (multi-camera mode)

### `outlet.id`

- Type: `string`

### `outlet.name`

- Type: `string`

### `outlet.cameras`

- Type: `list[{id, rtsp_url}]`
- Untuk security, isi `rtsp_url` dari env placeholder.
- Optional field per camera: `roi: [x1, y1, x2, y2]`
  - Format: normalized `0.0 - 1.0` (recommended)
  - Fungsi: batasi area deteksi per kamera agar false-positive dan beban inference turun.
  - Cara gambar ROI cepat:
    - `python scripts/draw_roi.py --camera-id cam_01`
    - Drag area di window, tekan `C` untuk confirm.
    - Copy output `roi: [...]` ke kamera terkait di YAML.

### `outlet.target_spg_ids`

- Type: `list[string]`

## 8. inference

### `inference.frame_skip`

- Type: `int`
- `0` = proses semua frame

### `inference.max_frame_height`

- Type: `int`

### `inference.max_frame_width`

- Type: `int`

## 9. notification

### `notification.telegram_enabled`

- Type: `bool`

### `notification.telegram_bot_token_env`

- Type: `string`
- Default: `SPG_TELEGRAM_BOT_TOKEN`

### `notification.telegram_chat_id_env`

- Type: `string`
- Default: `SPG_TELEGRAM_CHAT_ID`

### `notification.timeout_sec`

- Type: `int`

### `notification.max_retries`

- Type: `int`

### `notification.retry_backoff_base_sec`

- Type: `int`

### `notification.retry_after_default_sec`

- Type: `int`

## 10. runtime

### Loop

- `runtime.worker_idle_sleep_sec` (`float`)
- `runtime.main_loop_sleep_sec` (`float`)

### Supervisor (self-healing)

- `runtime.supervisor_restart_cooldown_sec` (`float`)
- `runtime.supervisor_max_restarts_per_minute` (`int`)

### Adaptive degrade

- `runtime.auto_degrade_enabled` (`bool`)
- `runtime.auto_degrade_lag_high_ms` (`float`)
- `runtime.auto_degrade_lag_low_ms` (`float`)
- `runtime.auto_degrade_high_streak` (`int`)
- `runtime.auto_degrade_low_streak` (`int`)
- `runtime.auto_degrade_max_frame_skip` (`int`)

### Preview persistence

- `runtime.preview_raw_enabled` (`bool`)
- `runtime.preview_frame_save_interval_sec` (`float`)
- `runtime.preview_frame_width` (`int`)
- `runtime.preview_jpeg_quality` (`int`)

## 11. dashboard

- `dashboard.host` (`string`)
- `dashboard.port` (`int`)
- `dashboard.reload` (`bool`)
- `dashboard.live_window_seconds` (`int`)
- `dashboard.recent_events_limit` (`int`)
- `dashboard.stream_frame_interval_sec` (`float`)
- `dashboard.stream_error_sleep_sec` (`float`)
- `dashboard.stream_missing_frame_sleep_sec` (`float`)

## 12. Required Environment Variables

- `RTSP_CAM_01_URL`
- `RTSP_CAM_02_URL`
- `RTSP_CAM_03_URL`
- `RTSP_CAM_04_URL`

Optional:

- `SPG_TELEGRAM_BOT_TOKEN`
- `SPG_TELEGRAM_CHAT_ID`
- `APP_ENV`
- `APP_CONFIG_PATH`

## 13. Profile Recommendations

### Demo

- `process_fps` lebih tinggi
- `frame_skip` dasar rendah (`0` atau `1`)
- stream interval lebih cepat

### Production

- `process_fps` moderat
- `frame_skip` dasar `1`
- auto-degrade tetap aktif untuk spike handling
- preview width/quality lebih hemat
