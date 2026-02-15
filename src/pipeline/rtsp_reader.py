import time
import cv2


class RTSPReader:
    def __init__(self, rtsp_url: str, process_fps: int):
        self.rtsp_url = rtsp_url
        self.process_fps = max(1, int(process_fps))
        self.cap = None
        self._last_emit = 0.0
        self._interval = 1.0 / self.process_fps


    def start(self):
        self.cap = cv2.VideoCapture(self.rtsp_url)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open RTSP stream: {self.rtsp_url}")

    
    def read_throttled(self):
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok:
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