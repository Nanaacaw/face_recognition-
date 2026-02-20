import os
import yaml
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional


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
    execution_providers: list[str] = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    det_size: tuple[int, int] | list[int] = [640, 640]


class PresenceConfig(BaseModel):
    grace_seconds: int
    absent_seconds: int


class StorageConfig(BaseModel):
    data_dir: str
    snapshot_enabled: bool
    snapshot_retention_days: int


# single-camera
class TargetConfig(BaseModel):
    spg_ids: list[str] = []
    outlet_id: str = ""
    camera_id: str = ""


# multi-camera outlet
class CameraEntry(BaseModel):
    id: str
    rtsp_url: str


class OutletConfig(BaseModel):
    id: str
    name: str = ""
    cameras: list[CameraEntry] = []
    target_spg_ids: list[str] = []


class InferenceConfig(BaseModel):
    """Settings for the centralized Inference Server."""
    frame_skip: int = 0  # Skip N frames between inferences (0 = process every frame)
    max_frame_height: int = 720  # Max frame height for shared memory buffer
    max_frame_width: int = 1280  # Max frame width for shared memory buffer


class DevConfig(BaseModel):
    simulate: bool = False
    video_files: list[str] = []


class AppConfig(BaseModel):
    camera: CameraConfig
    recognition: RecognitionConfig
    presence: PresenceConfig
    storage: StorageConfig
    target: TargetConfig = TargetConfig()
    outlet: OutletConfig | None = None
    inference: InferenceConfig = InferenceConfig()
    dev: DevConfig = DevConfig()

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