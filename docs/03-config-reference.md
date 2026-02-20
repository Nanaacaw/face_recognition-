# face_recog - Configuration Reference

Semua parameter runtime dibaca dari file YAML.

## Config Resolution Order

1. `APP_CONFIG_PATH` (jika diisi, langsung pakai path ini)
2. `APP_ENV` -> `configs/app.<env>.yaml`
3. Default environment: `dev`

Contoh:

```env
APP_ENV=dev
# atau:
APP_CONFIG_PATH=./configs/app.custom.yaml
```

---

## 1) camera

### `camera.source`
- Type: `string`
- Allowed: `webcam | rtsp`

### `camera.webcam_index`
- Type: `int`
- Used when: `camera.source=webcam`

### `camera.rtsp_url`
- Type: `string`
- Used when: `camera.source=rtsp`

### `camera.process_fps`
- Type: `int`
- Recommendation: `3-5`

### `camera.preview`
- Type: `bool`
- Description: tampilkan preview OpenCV.

---

## 2) recognition

### `recognition.threshold`
- Type: `float` (`0.0-1.0`)
- Typical: `0.40-0.55`

### `recognition.min_consecutive_hits`
- Type: `int`
- Typical: `2-3`

### `recognition.model_name`
- Type: `string`
- Default: `buffalo_s`
- Allowed: `buffalo_s | buffalo_l`

### `recognition.execution_providers`
- Type: `list[string]`
- Default: `["CUDAExecutionProvider", "CPUExecutionProvider"]`

### `recognition.det_size`
- Type: `list[int, int]` atau `tuple[int, int]`
- Default: `[640, 640]`

---

## 3) presence

### `presence.grace_seconds`
- Type: `int`
- Typical: `15-30`

### `presence.absent_seconds`
- Type: `int`
- Default: `300`

---

## 4) storage

### `storage.data_dir`
- Type: `string`
- Default: `./data`

### `storage.snapshot_enabled`
- Type: `bool`

### `storage.snapshot_retention_days`
- Type: `int`
- Recommendation: dev `3-7`, prod `7-30`

### `storage.sim_output_subdir`
- Type: `string`
- Default: `sim_output`
- Description: output multi-camera (`outlet_state`, events, preview frame per kamera).

### `storage.gallery_subdir`
- Type: `string`
- Default: `gallery`
- Description: metadata gallery dan face crop terakhir.

---

## 5) target (single camera mode)

### `target.spg_ids`
- Type: `list[string]`

### `target.outlet_id`
- Type: `string`

### `target.camera_id`
- Type: `string`

---

## 6) outlet (multi-camera mode)

### `outlet.id`
- Type: `string`

### `outlet.name`
- Type: `string`

### `outlet.cameras`
- Type: `list[{id, rtsp_url}]`

### `outlet.target_spg_ids`
- Type: `list[string]`

---

## 7) inference

### `inference.frame_skip`
- Type: `int`
- Default: `0`
- Description: `0` proses semua frame, `2` proses 1 dari 3 frame.

### `inference.max_frame_height`
- Type: `int`
- Default: `720`

### `inference.max_frame_width`
- Type: `int`
- Default: `1280`

---

## 8) notification

### `notification.telegram_enabled`
- Type: `bool`
- Default: `true`

### `notification.telegram_bot_token_env`
- Type: `string`
- Default: `SPG_TELEGRAM_BOT_TOKEN`

### `notification.telegram_chat_id_env`
- Type: `string`
- Default: `SPG_TELEGRAM_CHAT_ID`

### `notification.timeout_sec`
- Type: `int`
- Default: `15`

### `notification.max_retries`
- Type: `int`
- Default: `3`

### `notification.retry_backoff_base_sec`
- Type: `int`
- Default: `2`

### `notification.retry_after_default_sec`
- Type: `int`
- Default: `5`

---

## 9) runtime

### `runtime.worker_idle_sleep_sec`
- Type: `float`
- Default: `0.05`

### `runtime.main_loop_sleep_sec`
- Type: `float`
- Default: `0.05`

### `runtime.preview_frame_save_interval_sec`
- Type: `float`
- Default: `0.2`

### `runtime.preview_frame_width`
- Type: `int`
- Default: `640`

### `runtime.preview_jpeg_quality`
- Type: `int`
- Default: `80`

---

## 10) dashboard

### `dashboard.host`
- Type: `string`
- Default: `0.0.0.0`

### `dashboard.port`
- Type: `int`
- Default: `8000`

### `dashboard.reload`
- Type: `bool`
- Default: `true` (biasanya `false` di staging/prod)

### `dashboard.live_window_seconds`
- Type: `int`
- Default: `10`

### `dashboard.recent_events_limit`
- Type: `int`
- Default: `50`

### `dashboard.stream_frame_interval_sec`
- Type: `float`
- Default: `0.2`

### `dashboard.stream_error_sleep_sec`
- Type: `float`
- Default: `0.5`

### `dashboard.stream_missing_frame_sleep_sec`
- Type: `float`
- Default: `1.0`

---

## 11) Environment Variables

Required for Telegram notification:

- `SPG_TELEGRAM_BOT_TOKEN`
- `SPG_TELEGRAM_CHAT_ID`

Optional:

- `APP_ENV` (`dev`, `staging`, `prod`)
- `APP_CONFIG_PATH` (custom config path)

---

## 12) Tuning Order (Recommended)

1. `recognition.threshold`
2. `recognition.min_consecutive_hits`
3. `presence.grace_seconds`
4. `camera.process_fps`
5. `inference.frame_skip`

---

## 13) Deployment Notes

- Centralized mode dijalankan via `make run` (production) atau `make simulate` (development simulation).
- Dashboard dijalankan via `make dashboard`.
- Jangan commit credential RTSP dan secret Telegram ke Git.
