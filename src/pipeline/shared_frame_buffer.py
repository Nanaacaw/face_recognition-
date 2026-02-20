"""
SharedFrameBuffer: Zero-copy frame passing between Camera Workers and InferenceServer.

Instead of pickling ~1.2MB numpy arrays through multiprocessing.Queue,
we use shared memory so workers write frames in-place and the server reads directly.

Usage:
    # At startup (main process):
    buf = SharedFrameBuffer.create("cam_01", max_height=720, max_width=1280)

    # In camera worker process:
    buf.write(frame_bgr)

    # In inference server process:
    frame = buf.read()

    # Cleanup:
    buf.close()
    buf.unlink()  # Only in main process
"""

from __future__ import annotations

import numpy as np
from multiprocessing import shared_memory, Lock
from dataclasses import dataclass


# Pre-calculated: 1280x720x3 = 2,764,800 bytes (~2.6MB)
# This covers up to 720p. For 1080p, increase max_height/max_width.
_DEFAULT_MAX_H = 720
_DEFAULT_MAX_W = 1280
_CHANNELS = 3


@dataclass(frozen=True)
class FrameMeta:
    """Metadata for the frame currently in the buffer."""
    height: int
    width: int
    frame_id: int
    timestamp: float


class SharedFrameBuffer:
    """
    A single shared memory slot for one camera's latest frame.
    
    Memory layout:
      [0:4]   - height (int32)
      [4:8]   - width (int32)
      [8:16]  - frame_id (int64)
      [16:24] - timestamp (float64)
      [24:28] - valid flag (int32, 1=has frame, 0=empty)
      [28:]   - raw BGR pixel data (max_h * max_w * 3 bytes)
    """

    _HEADER_SIZE = 28  # 4+4+8+8+4 bytes

    def __init__(
        self,
        shm: shared_memory.SharedMemory,
        max_height: int,
        max_width: int,
        lock: Lock,
        is_creator: bool = False,
    ):
        self._shm = shm
        self._max_h = max_height
        self._max_w = max_width
        self._lock = lock
        self._is_creator = is_creator
        self._pixel_offset = self._HEADER_SIZE

    @classmethod
    def create(
        cls,
        name: str,
        max_height: int = _DEFAULT_MAX_H,
        max_width: int = _DEFAULT_MAX_W,
        lock: Lock | None = None,
    ) -> SharedFrameBuffer:
        """Create a NEW shared memory buffer. Call from main process only."""
        total = cls._HEADER_SIZE + (max_height * max_width * _CHANNELS)
        shm = shared_memory.SharedMemory(name=f"sfb_{name}", create=True, size=total)
        
        # Zero out valid flag
        np.frombuffer(shm.buf, dtype=np.int32, count=1, offset=24)[:] = 0

        return cls(
            shm=shm,
            max_height=max_height,
            max_width=max_width,
            lock=lock or Lock(),
            is_creator=True,
        )

    @classmethod
    def attach(
        cls,
        name: str, 
        max_height: int = _DEFAULT_MAX_H,
        max_width: int = _DEFAULT_MAX_W,
        lock: Lock | None = None,
    ) -> SharedFrameBuffer:
        """Attach to an EXISTING shared memory buffer. Call from child processes."""
        shm = shared_memory.SharedMemory(name=f"sfb_{name}", create=False)
        return cls(
            shm=shm,
            max_height=max_height,
            max_width=max_width,
            lock=lock or Lock(),
            is_creator=False,
        )

    def write(self, frame_bgr: np.ndarray, frame_id: int = 0, timestamp: float = 0.0) -> bool:
        """Write a frame into shared memory. Returns False if frame too large."""
        h, w = frame_bgr.shape[:2]
        if h > self._max_h or w > self._max_w:
            return False

        with self._lock:
            buf = self._shm.buf
            
            # Write header
            np.frombuffer(buf, dtype=np.int32, count=1, offset=0)[:] = h
            np.frombuffer(buf, dtype=np.int32, count=1, offset=4)[:] = w
            np.frombuffer(buf, dtype=np.int64, count=1, offset=8)[:] = frame_id
            np.frombuffer(buf, dtype=np.float64, count=1, offset=16)[:] = timestamp

            # Write pixel data
            flat = frame_bgr.tobytes()
            buf[self._pixel_offset : self._pixel_offset + len(flat)] = flat

            # Set valid flag LAST (acts as memory fence)
            np.frombuffer(buf, dtype=np.int32, count=1, offset=24)[:] = 1

        return True

    def read(self) -> tuple[np.ndarray | None, FrameMeta | None]:
        """
        Read the latest frame from shared memory.
        Returns (frame_bgr, meta) or (None, None) if no valid frame.
        """
        with self._lock:
            buf = self._shm.buf

            # Check valid flag
            valid = int(np.frombuffer(buf, dtype=np.int32, count=1, offset=24)[0])
            if valid == 0:
                return None, None

            # Read header
            h = int(np.frombuffer(buf, dtype=np.int32, count=1, offset=0)[0])
            w = int(np.frombuffer(buf, dtype=np.int32, count=1, offset=4)[0])
            fid = int(np.frombuffer(buf, dtype=np.int64, count=1, offset=8)[0])
            ts = float(np.frombuffer(buf, dtype=np.float64, count=1, offset=16)[0])

            # Read pixel data (copy out of shared memory)
            nbytes = h * w * _CHANNELS
            raw = bytes(buf[self._pixel_offset : self._pixel_offset + nbytes])

        frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, _CHANNELS)
        meta = FrameMeta(height=h, width=w, frame_id=fid, timestamp=ts)
        return frame, meta

    def close(self):
        """Close this process's view. Safe to call multiple times."""
        try:
            self._shm.close()
        except Exception:
            pass

    def unlink(self):
        """Remove the shared memory. Only call from the creator (main process)."""
        if self._is_creator:
            try:
                self._shm.unlink()
            except Exception:
                pass
