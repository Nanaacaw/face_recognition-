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

def load_settings(config_path: str | None = None) -> AppConfig:
    load_dotenv()
    
    if config_path is None:
        env = os.getenv("APP_ENV", "dev")
        config_path = f"configs/app.{env}.yaml"

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AppConfig.model_validate(raw)