from __future__ import annotations

import argparse
import cv2

from src.settings.settings import load_settings
from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.face_detector import FaceDetector


def _resolve_webcam_index(webcam_index: int | None) -> int:
    return 0 if webcam_index is None else webcam_index


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
        _resolve_webcam_index(cfg.camera.webcam_index),
        cfg.camera.process_fps,
    )
    detector = FaceDetector(
        name=cfg.recognition.model_name,
        providers=cfg.recognition.execution_providers,
        det_size=cfg.recognition.det_size,
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
            webcam_index=_resolve_webcam_index(cfg.camera.webcam_index),
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
            model_name=cfg.recognition.model_name,
            execution_providers=cfg.recognition.execution_providers,
            det_size=cfg.recognition.det_size,
            enable_notifier=cfg.notification.telegram_enabled,
            notifier_token_env=cfg.notification.telegram_bot_token_env,
            notifier_chat_id_env=cfg.notification.telegram_chat_id_env,
            notifier_timeout_sec=cfg.notification.timeout_sec,
            notifier_max_retries=cfg.notification.max_retries,
            notifier_retry_backoff_base_sec=cfg.notification.retry_backoff_base_sec,
            notifier_retry_after_default_sec=cfg.notification.retry_after_default_sec,
            preview_frame_save_interval_sec=cfg.runtime.preview_frame_save_interval_sec,
            preview_frame_width=cfg.runtime.preview_frame_width,
            preview_jpeg_quality=cfg.runtime.preview_jpeg_quality,
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
            webcam_index=_resolve_webcam_index(cfg.camera.webcam_index),
            process_fps=cfg.camera.process_fps,
            samples=args.samples,
            model_name=cfg.recognition.model_name,
            execution_providers=cfg.recognition.execution_providers,
            det_size=cfg.recognition.det_size,
        )
        return


if __name__ == "__main__":
    main()
