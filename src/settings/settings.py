import os
import yaml
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv


class CameraConfig(BaseModel):
    source: str
    webcam_index: int | None = None
    rtsp_url: str | None = None
    process_fps: int
    preview: bool


class RecognitionConfig(BaseModel):
    threshold: float
    min_consecutive_hits: int


class PresenceConfig(BaseModel):
    grace_seconds: int
    absent_seconds: int


class StorageConfig(BaseModel):
    data_dir: str
    snapshot_enabled: bool
    snapshot_retention_days: int


class TargetConfig(BaseModel):
    spg_ids: list[str]
    outlet_id: str
    camera_id: str


class AppConfig(BaseModel):
    camera: CameraConfig
    recognition: RecognitionConfig
    presence: PresenceConfig
    storage: StorageConfig
    target: TargetConfig

def load_settings() -> AppConfig:
    load_dotenv()

    env = os.getenv("APP_ENV", "dev")
    config_path = Path("configs") / f"app.{env}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)

    return AppConfig(**raw_config)