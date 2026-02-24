import random
import re
import time
import os

import cv2

from src.settings.logger import logger


_CRED_IN_URL = re.compile(r"://([^/@:]+):([^/@]+)@")


def _mask_rtsp_url(url: str) -> str:
    """Mask credentials in URL before logging."""
    if not url:
        return url
    return _CRED_IN_URL.sub(r"://\1:***@", url)


class RTSPReader:
    def __init__(self, rtsp_url: str, process_fps: int):
        self.rtsp_url = rtsp_url
        self._safe_url = _mask_rtsp_url(rtsp_url)
        self.process_fps = max(1, int(process_fps))
        self.cap: cv2.VideoCapture | None = None
        self._last_emit = 0.0
        self._interval = 1.0 / self.process_fps

        self.loop = False

        # Reconnect policy
        self.reconnect_base_delay = 1.0
        self.reconnect_max_delay = 30.0
        self.reconnect_jitter_ratio = 0.2
        self._reconnect_attempt = 0
        self._next_reconnect_ts = 0.0

    def set_loop(self, loop: bool):
        self.loop = loop

    def _open_capture(self) -> cv2.VideoCapture:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        cap = cv2.VideoCapture(self.rtsp_url)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def _reset_reconnect_state(self):
        self._reconnect_attempt = 0
        self._next_reconnect_ts = 0.0

    def _schedule_next_reconnect(self):
        self._reconnect_attempt += 1
        delay = min(
            self.reconnect_max_delay,
            self.reconnect_base_delay * (2 ** max(0, self._reconnect_attempt - 1)),
        )
        jitter = random.uniform(0.0, delay * self.reconnect_jitter_ratio)
        wait_sec = delay + jitter
        self._next_reconnect_ts = time.time() + wait_sec
        logger.warning(
            f"RTSP reconnect scheduled in {wait_sec:.1f}s "
            f"(attempt={self._reconnect_attempt}) for {self._safe_url}"
        )

    def start(self):
        logger.info(f"Connecting to RTSP stream: {self._safe_url}")
        self.cap = self._open_capture()
        if not self.cap.isOpened():
            logger.error(f"Cannot open RTSP stream: {self._safe_url}")
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            self._schedule_next_reconnect()
        else:
            self._reset_reconnect_state()

    def _reconnect(self) -> bool:
        now = time.time()
        if now < self._next_reconnect_ts:
            return False

        logger.warning(f"Attempting to reconnect RTSP: {self._safe_url}")
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass

        self.cap = self._open_capture()

        if self.cap.isOpened():
            logger.info("RTSP reconnected successfully.")
            self._reset_reconnect_state()
            return True

        try:
            self.cap.release()
        except Exception:
            pass
        self.cap = None
        self._schedule_next_reconnect()
        return False

    def read_throttled(self):
        # Auto-reconnect if connection is lost or not initialized.
        if self.cap is None or not self.cap.isOpened():
            if not self._reconnect():
                return None

        ok, frame = self.cap.read()
        if not ok:
            if self.loop and self.cap is not None:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()

            if not ok:
                logger.warning("RTSP read failed (EOF/Error). Triggering reconnect.")
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
                self._schedule_next_reconnect()
                return None

        now = time.time()
        if now - self._last_emit >= self._interval:
            self._last_emit = now
            return frame
        return None

    def stop(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
