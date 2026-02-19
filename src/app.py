from __future__ import annotations

import argparse
import cv2

from src.settings.settings import load_settings
from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.face_detector import FaceDetector


def cmd_debug(config_path: str | None):
    cfg = load_settings(config_path)
    print("=== face_recog DEBUG MODE ===")
    print(cfg)

    # Optional: show ONNX providers (kalau onnxruntime ada)
    try:
        import onnxruntime as ort
        print("ONNX providers:", ort.get_available_providers())
    except Exception as e:
        print("[WARN] Could not read ONNX providers:", e)

    if not cfg.camera.preview:
        print("preview=false, only printing config.")
        return

    if cfg.camera.source != "webcam":
        print("debug preview currently supports webcam only.")
        return

    reader = WebcamReader(
        cfg.camera.webcam_index or 0,
        cfg.camera.process_fps,
    )
    detector = FaceDetector(
        name=getattr(cfg.recognition, "model_name", "buffalo_s"),
        providers=getattr(cfg.recognition, "execution_providers", None),
        det_size=tuple(getattr(cfg.recognition, "det_size", (640, 640)))
    )

    reader.start()
    detector.start()
    print("Webcam preview started. Press 'q' to quit.")

    try:
        while True:
            frame = reader.read_throttled()
            if frame is None:
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            faces = detector.detect(frame)

            for f in faces:
                x1, y1, x2, y2 = [int(v) for v in f.bbox]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                score = float(getattr(f, "det_score", 0.0))
                cv2.putText(
                    frame,
                    f"{score:.2f}",
                    (x1, max(0, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )

            cv2.imshow("face_recog | debug", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        reader.stop()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(prog="face_recog")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # debug
    p_debug = subparsers.add_parser("debug")
    p_debug.add_argument("--config", type=str, default=None)

    # run
    p_run = subparsers.add_parser("run")
    p_run.add_argument("--config", type=str, default=None)

    # enroll
    p_enroll = subparsers.add_parser("enroll")
    p_enroll.add_argument("--config", type=str, default=None)
    p_enroll.add_argument("--spg_id", required=True)
    p_enroll.add_argument("--name", required=True)
    p_enroll.add_argument("--samples", type=int, default=30)

    args = parser.parse_args()

    if args.command == "debug":
        cmd_debug(args.config)
        return

    if args.command == "run":
        cfg = load_settings(args.config)
        from src.commands.run_webcam import run_webcam_recognition

        run_webcam_recognition(
            data_dir=cfg.storage.data_dir,
            webcam_index=cfg.camera.webcam_index or 0,
            process_fps=cfg.camera.process_fps,
            threshold=cfg.recognition.threshold,
            grace_seconds=cfg.presence.grace_seconds,
            absent_seconds=cfg.presence.absent_seconds,
            outlet_id=cfg.target.outlet_id,
            camera_id=cfg.target.camera_id,
            target_spg_ids=cfg.target.spg_ids,
            camera_source=cfg.camera.source,
            rtsp_url=cfg.camera.rtsp_url,
            preview=cfg.camera.preview,
            model_name=getattr(cfg.recognition, "model_name", "buffalo_s"),
            execution_providers=getattr(cfg.recognition, "execution_providers", None),
            det_size=getattr(cfg.recognition, "det_size", (640, 640)),
        )
        return

    if args.command == "enroll":
        cfg = load_settings(args.config)
        if cfg.camera.source != "webcam":
            print("[ENROLL] Enrollment MVP sekarang hanya support webcam.")
            print("Pakai config yang camera.source=webcam untuk enroll.")
            return

        from src.enrollment.enroll_webcam import enroll_from_webcam

        enroll_from_webcam(
            spg_id=args.spg_id,
            name=args.name,
            data_dir=cfg.storage.data_dir,
            webcam_index=cfg.camera.webcam_index or 0,
            process_fps=cfg.camera.process_fps,
            samples=args.samples,
            model_name=getattr(cfg.recognition, "model_name", "buffalo_s"),
            execution_providers=getattr(cfg.recognition, "execution_providers", None),
            det_size=tuple(getattr(cfg.recognition, "det_size", (640, 640))),
        )
        return


if __name__ == "__main__":
    main()
