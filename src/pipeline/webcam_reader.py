import time
import cv2


class WebcamReader:
    def __init__(self, index: int, process_fps: int):
        self.index = index
        self.process_fps = max(1, int(process_fps))
        self.cap: cv2.VideoCapture | None = None

        self.frame_interval = 1.0 / self.process_fps
        self._last_emit = 0.0

    def start(self) -> None:
        self.cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open webcam index {self.index}")

    def read_throttled(self):
        """Return a frame at ~process_fps; returns None for dropped frames."""
        assert self.cap is not None
        ok, frame = self.cap.read()
        if not ok:
            return None

        now = time.time()
        if now - self._last_emit >= self.frame_interval:
            self._last_emit = now
            return frame
        return None

    def stop(self) -> None:
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()
