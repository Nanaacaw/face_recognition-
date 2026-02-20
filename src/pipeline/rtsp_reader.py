import time
import cv2
from src.settings.logger import logger

class RTSPReader:
    def __init__(self, rtsp_url: str, process_fps: int):
        self.rtsp_url = rtsp_url
        self.process_fps = max(1, int(process_fps))
        self.cap = None
        self._last_emit = 0.0
        self._interval = 1.0 / self.process_fps
        self.loop = False
        self.reconnect_delay = 5  # sec
        self.last_reconnect_time = 0

    def set_loop(self, loop: bool):
        self.loop = loop

    def start(self):
        logger.info(f"Connecting to RTSP stream: {self.rtsp_url}")
        self.cap = cv2.VideoCapture(self.rtsp_url)
        if not self.cap.isOpened():
            logger.error(f"Cannot open RTSP stream: {self.rtsp_url}")
            self.cap = None

    def _reconnect(self):
        now = time.time()
        if now - self.last_reconnect_time < self.reconnect_delay:
            return False
            
        logger.warning(f"Attempting to reconnect RTSP: {self.rtsp_url}")
        if self.cap is not None:
            self.cap.release()
            
        self.cap = cv2.VideoCapture(self.rtsp_url)
        self.last_reconnect_time = now
        
        if self.cap.isOpened():
            logger.info("RTSP Reconnected successfully.")
            return True
        else:
            return False

    def read_throttled(self):
        # Auto-reconnect if connection lost or never established
        if self.cap is None or not self.cap.isOpened():
            if not self._reconnect():
                return None

        ok, frame = self.cap.read()
        if not ok:
            if self.loop:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
            
            if not ok:
                logger.warning("RTSP read failed (EOF or Error). Triggering reconnect.")
                self.cap.release()
                self.cap = None
                return None

        now = time.time()
        if now - self._last_emit >= self._interval:
            self._last_emit = now
            return frame
        return None

    def stop (self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
