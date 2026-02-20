import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def setup_logger(name="face_recog", log_dir="logs", level=logging.INFO):
    """
    Setup a logger that writes to both console (stdout) and a rotating file.
    Keep it simple: 1 log file, max 5MB, keep 3 backups.
    """
    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding handlers multiple times
    if logger.hasHandlers():
        return logger

    # Format: [TIME] [LEVEL] Message
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler (Print to terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler (Save to file with rotation)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# Singleton logger instance
logger = setup_logger()
