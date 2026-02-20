import os
import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv


DEFAULT_APP_ENV = "dev"
DEFAULT_CONFIG_TEMPLATE = "configs/app.{env}.yaml"


class CameraConfig(BaseModel):
    source: str
    webcam_index: int | None = None
    rtsp_url: str | None = None
    process_fps: int
    preview: bool


class RecognitionConfig(BaseModel):
    threshold: float
    min_consecutive_hits: int
    model_name: str = "buffalo_s"
    execution_providers: list[str] = Field(
        default_factory=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"]
    )
    det_size: tuple[int, int] = (640, 640)


class PresenceConfig(BaseModel):
    grace_seconds: int
    absent_seconds: int


class StorageConfig(BaseModel):
    data_dir: str
    snapshot_enabled: bool
    snapshot_retention_days: int
    sim_output_subdir: str = "sim_output"
    gallery_subdir: str = "gallery"


# single-camera
class TargetConfig(BaseModel):
    spg_ids: list[str] = Field(default_factory=list)
    outlet_id: str = ""
    camera_id: str = ""


# multi-camera outlet
class CameraEntry(BaseModel):
    id: str
    rtsp_url: str


class OutletConfig(BaseModel):
    id: str
    name: str = ""
    cameras: list[CameraEntry] = Field(default_factory=list)
    target_spg_ids: list[str] = Field(default_factory=list)


class InferenceConfig(BaseModel):
    """Settings for the centralized Inference Server."""
    frame_skip: int = 0  # Skip N frames between inferences (0 = process every frame)
    max_frame_height: int = 720  # Max frame height for shared memory buffer
    max_frame_width: int = 1280  # Max frame width for shared memory buffer


class DevConfig(BaseModel):
    simulate: bool = False
    video_files: list[str] = Field(default_factory=list)


class NotificationConfig(BaseModel):
    telegram_enabled: bool = True
    telegram_bot_token_env: str = "SPG_TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "SPG_TELEGRAM_CHAT_ID"
    timeout_sec: int = 15
    max_retries: int = 3
    retry_backoff_base_sec: int = 2
    retry_after_default_sec: int = 5


class RuntimeConfig(BaseModel):
    # Loop intervals
    worker_idle_sleep_sec: float = 0.05
    main_loop_sleep_sec: float = 0.05
    # Preview frame persistence
    preview_frame_save_interval_sec: float = 0.2
    preview_frame_width: int = 640
    preview_jpeg_quality: int = 80


class DashboardConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    live_window_seconds: int = 10
    recent_events_limit: int = 50
    stream_frame_interval_sec: float = 0.2
    stream_error_sleep_sec: float = 0.5
    stream_missing_frame_sleep_sec: float = 1.0


class AppConfig(BaseModel):
    camera: CameraConfig
    recognition: RecognitionConfig
    presence: PresenceConfig
    storage: StorageConfig
    target: TargetConfig = Field(default_factory=TargetConfig)
    outlet: OutletConfig | None = None
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    dev: DevConfig = Field(default_factory=DevConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)


def load_settings(config_path: str | None = None) -> AppConfig:
    load_dotenv()

    if config_path is None:
        config_path = os.getenv("APP_CONFIG_PATH", "").strip() or None

    if config_path is None:
        env = os.getenv("APP_ENV", DEFAULT_APP_ENV).strip() or DEFAULT_APP_ENV
        config_path = DEFAULT_CONFIG_TEMPLATE.format(env=env)

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AppConfig.model_validate(raw)
