# Configuration Reference

Dokumen ini mengacu ke schema aktual di `src/settings/settings.py`.

## 1. Resolusi Config

Urutan prioritas:

1. Argumen CLI `--config`
2. Env `APP_CONFIG_PATH`
3. Env `APP_ENV` -> `configs/app.<env>.yaml` (default `dev`)

## 2. `camera`

Dipakai terutama oleh mode single-camera (`src.app run`) dan sebagai source `process_fps` di mode outlet.

- `source` (`string`): `webcam | rtsp`
- `webcam_index` (`int | null`)
- `rtsp_url` (`string | null`)
- `process_fps` (`int`)
- `preview` (`bool`)

## 3. `recognition`

- `threshold` (`float`): threshold similarity matcher
- `min_consecutive_hits` (`int`): minimum streak match sebelum event `SPG_SEEN` diterima
- `min_det_score` (`float`): minimum detector confidence
- `min_face_width_px` (`int`): minimum lebar wajah
- `model_name` (`string`): contoh `buffalo_s`, `buffalo_l`
- `execution_providers` (`list[string]`): ONNX provider priority
- `det_size` (`tuple[int,int] | list[int,int]`)

## 4. `presence`

- `grace_seconds` (`int`)
- `absent_seconds` (`int`)

## 5. `storage`

- `data_dir` (`string`)
- `snapshot_enabled` (`bool`)
- `snapshot_retention_days` (`int`)
- `sim_output_subdir` (`string`, default `sim_output`)
- `gallery_subdir` (`string`, default `gallery`)

Catatan:

- `sim_output_subdir` dipakai pipeline + dashboard untuk state/health/events/live-frame
- `gallery_subdir` dipakai enrollment, gallery loader, dan endpoint gallery dashboard

## 6. `target` (single-camera mode)

- `spg_ids` (`list[string]`)
- `outlet_id` (`string`)
- `camera_id` (`string`)

## 7. `outlet` (multi-camera mode / `run_outlet`)

- `id` (`string`)
- `name` (`string`)
- `cameras` (`list[CameraEntry]`)
  - `id` (`string`)
  - `rtsp_url` (`string`)
  - `roi` (`tuple[float,float,float,float] | null`)
- `target_spg_ids` (`list[string]`)

`run_outlet` akan exit jika blok `outlet` tidak ada.

### ROI Notes

- Format normalized dianjurkan: `[x1, y1, x2, y2]` rentang `0.0..1.0`
- Pixel absolute juga didukung
- ROI invalid/kecil akan diabaikan

Tool bantu:

- `make draw-roi`
- `make draw-roi CAMERA_ID=cam_01`

## 8. `inference`

- `frame_skip` (`int`): 0 = proses semua frame
- `max_frame_height` (`int`)
- `max_frame_width` (`int`)

## 9. `notification`

- `telegram_enabled` (`bool`)
- `telegram_bot_token_env` (`string`)
- `telegram_chat_id_env` (`string`)
- `timeout_sec` (`int`)
- `max_retries` (`int`)
- `retry_backoff_base_sec` (`int`)
- `retry_after_default_sec` (`int`)

## 10. `dev`

- `simulate` (`bool`)
- `video_files` (`list[string]`)

Jika `simulate=true` dan `video_files` terisi, `run_outlet` pakai file video sebagai source.

## 11. `runtime`

### Loop

- `worker_idle_sleep_sec` (`float`)
- `main_loop_sleep_sec` (`float`)

### Supervisor

- `supervisor_restart_cooldown_sec` (`float`)
- `supervisor_max_restarts_per_minute` (`int`)

### Auto-degrade

- `auto_degrade_enabled` (`bool`)
- `auto_degrade_lag_high_ms` (`float`)
- `auto_degrade_lag_low_ms` (`float`)
- `auto_degrade_high_streak` (`int`)
- `auto_degrade_low_streak` (`int`)
- `auto_degrade_max_frame_skip` (`int`)

### Preview writer

- `preview_raw_enabled` (`bool`)
- `preview_frame_save_interval_sec` (`float`)
- `preview_frame_width` (`int`)
- `preview_jpeg_quality` (`int`)

## 12. `dashboard`

- `host` (`string`)
- `port` (`int`)
- `reload` (`bool`)
- `live_window_seconds` (`int`)
- `recent_events_limit` (`int`)
- `stream_frame_interval_sec` (`float`)
- `stream_error_sleep_sec` (`float`)
- `stream_missing_frame_sleep_sec` (`float`)

## 13. Environment Variables

Wajib untuk mode RTSP outlet:

- `RTSP_CAM_01_URL`
- `RTSP_CAM_02_URL`
- `RTSP_CAM_03_URL`
- `RTSP_CAM_04_URL`

Opsional:

- `SPG_TELEGRAM_BOT_TOKEN`
- `SPG_TELEGRAM_CHAT_ID`
- `APP_ENV`
- `APP_CONFIG_PATH`

## 14. Runtime Control File

Path:

- `<storage.data_dir>/<storage.sim_output_subdir>/runtime_control.json`

Field yang dibaca:

- `frame_skip`
- `min_consecutive_hits`
- `min_det_score`
- `min_face_width_px`
- `auto_degrade_enabled`

## 15. Profil Praktis

### Demo/dev

- `frame_skip` rendah
- `process_fps` lebih tinggi
- stream interval kecil

### Prod

- `frame_skip` moderat
- auto-degrade aktif
- preview width/quality lebih hemat
