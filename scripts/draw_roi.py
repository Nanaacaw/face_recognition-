from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import cv2


WINDOW_NAME = "ROI Drawer"


@dataclass
class RoiState:
    drawing: bool = False
    start: tuple[int, int] | None = None
    end: tuple[int, int] | None = None

    def reset(self) -> None:
        self.drawing = False
        self.start = None
        self.end = None

    def bbox(self) -> tuple[int, int, int, int] | None:
        if self.start is None or self.end is None:
            return None
        x1, y1 = self.start
        x2, y2 = self.end
        if x1 == x2 or y1 == y2:
            return None
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)
        return (left, top, right, bottom)


def _resolve_image_path(camera_id: str | None, image_path: str | None, data_dir: str) -> str:
    if image_path:
        return image_path

    if camera_id:
        raw_path = os.path.join(data_dir, camera_id, "snapshots", "latest_raw_frame.jpg")
        ai_path = os.path.join(data_dir, camera_id, "snapshots", "latest_frame.jpg")
        if os.path.exists(raw_path):
            return raw_path
        if os.path.exists(ai_path):
            return ai_path
        raise FileNotFoundError(f"No snapshot found for camera_id={camera_id}")

    for name in sorted(os.listdir(data_dir)):
        cam_dir = os.path.join(data_dir, name, "snapshots")
        raw_path = os.path.join(cam_dir, "latest_raw_frame.jpg")
        ai_path = os.path.join(cam_dir, "latest_frame.jpg")
        if os.path.exists(raw_path):
            return raw_path
        if os.path.exists(ai_path):
            return ai_path

    raise FileNotFoundError(f"No camera snapshot found under {data_dir}")


def _mouse_callback(event: int, x: int, y: int, _flags: int, state: RoiState) -> None:
    if event == cv2.EVENT_LBUTTONDOWN:
        state.drawing = True
        state.start = (x, y)
        state.end = (x, y)
        return

    if event == cv2.EVENT_MOUSEMOVE and state.drawing:
        state.end = (x, y)
        return

    if event == cv2.EVENT_LBUTTONUP and state.drawing:
        state.drawing = False
        state.end = (x, y)


def _to_normalized(bbox: tuple[int, int, int, int], width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 / width, y1 / height, x2 / width, y2 / height)


def main() -> int:
    parser = argparse.ArgumentParser(description="Draw ROI rectangle and print normalized coordinates.")
    parser.add_argument("--camera-id", type=str, default=None, help="Camera id (example: cam_01)")
    parser.add_argument("--image", type=str, default=None, help="Direct path to an image file")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=os.path.join("data", "sim_output"),
        help="Base directory for camera snapshots",
    )
    args = parser.parse_args()

    try:
        img_path = _resolve_image_path(args.camera_id, args.image, args.data_dir)
    except Exception as exc:
        print(f"[ERR] {exc}")
        return 1

    frame = cv2.imread(img_path)
    if frame is None:
        print(f"[ERR] Failed to read image: {img_path}")
        return 1

    h, w = frame.shape[:2]
    state = RoiState()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW_NAME, _mouse_callback, state)

    print(f"[ROI] Source: {img_path}")
    print("[ROI] Drag mouse to draw rectangle.")
    print("[ROI] Controls: C/Enter=confirm, R=reset, Q/Esc=quit")

    while True:
        canvas = frame.copy()
        bbox = state.bbox()

        if bbox is not None:
            x1, y1, x2, y2 = bbox
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
            nx1, ny1, nx2, ny2 = _to_normalized(bbox, w, h)
            text = (
                f"px=({x1},{y1})-({x2},{y2})  "
                f"norm=[{nx1:.4f}, {ny1:.4f}, {nx2:.4f}, {ny2:.4f}]"
            )
            cv2.putText(canvas, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        cv2.putText(
            canvas,
            "Drag ROI | C/Enter: confirm | R: reset | Q/Esc: quit",
            (10, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )

        cv2.imshow(WINDOW_NAME, canvas)
        key = cv2.waitKey(20) & 0xFF

        if key in (ord("q"), 27):
            print("[ROI] Canceled.")
            cv2.destroyAllWindows()
            return 0

        if key == ord("r"):
            state.reset()
            continue

        if key in (ord("c"), 13):
            if bbox is None:
                print("[ROI] Draw a rectangle first.")
                continue

            nx1, ny1, nx2, ny2 = _to_normalized(bbox, w, h)
            print("[ROI] Done.")
            print(f"roi: [{nx1:.4f}, {ny1:.4f}, {nx2:.4f}, {ny2:.4f}]")
            if args.camera_id:
                print(f"camera_id={args.camera_id}")
            cv2.destroyAllWindows()
            return 0


if __name__ == "__main__":
    sys.exit(main())
