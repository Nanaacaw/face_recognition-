import os
import glob
import time
from src.settings.logger import logger

class SnapshotCleaner:
    def __init__(self, data_dir: str, retention_days: int):
        self.data_dir = data_dir
        self.retention_days = retention_days
        self.retention_seconds = retention_days * 86400

    def clean(self):
        """
        Scan all camera directories for snapshots older than retention_days.
        Structure: data/sim_output/cam_XX/snapshots/*.jpg
        """
        if self.retention_days <= 0:
            logger.info("[Cleaner] Retention disabled (days <= 0).")
            return

        logger.info(f"[Cleaner] Starting cleanup. Retention: {self.retention_days} days.")
        now = time.time()
        count = 0
        total_size_mb = 0

        # Pattern: data_dir/sim_output/*/snapshots/*.jpg
        # We need to be careful not to delete 'latest_frame.jpg' or 'latest_XXX.jpg' if they are needed for current state
        # But usually 'latest_' files are overwritten constantly, so their mtime is new.
        # Historical snapshots are usually named with timestamp like "20240101_120000.jpg"
        
        # Search recursively
        # 1. Check sim_output/cam_*/snapshots/*.jpg
        # 2. Check data/snapshots/*.jpg (if any)
        
        search_paths = [
            os.path.join(self.data_dir, "sim_output", "*", "snapshots", "*.jpg"),
            os.path.join(self.data_dir, "snapshots", "*.jpg")
        ]
        
        for pattern in search_paths:
            files = glob.glob(pattern)
            for f in files:
                try:
                    stat = os.stat(f)
                    age = now - stat.st_mtime
                    
                    if age > self.retention_seconds:
                        size = stat.st_size
                        os.remove(f)
                        count += 1
                        total_size_mb += size / (1024 * 1024)
                except Exception as e:
                    logger.warning(f"[Cleaner] Failed to check/delete {f}: {e}")

        if count > 0:
            logger.info(f"[Cleaner] Deleted {count} old snapshots. Freed {total_size_mb:.2f} MB.")
        else:
            logger.info("[Cleaner] No old snapshots found.")
