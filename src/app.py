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

    # Optional: show ONNX providers
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
    detector = FaceDetector(det_size=(640, 640))

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


def cmd_run(config_path: str | None):
    cfg = load_settings(config_path)
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
    )


def cmd_enroll(config_path: str | None, spg_id: str, name: str, samples: int):
    cfg = load_settings(config_path)

    if cfg.camera.source != "webcam":
        print("[ENROLL] Enrollment MVP sekarang hanya support webcam.")
        print("Pakai config yang camera.source=webcam untuk enroll.")
        return

    from src.enrollment.enroll_webcam import enroll_from_webcam

    enroll_from_webcam(
        spg_id=spg_id,
        name=name,
        data_dir=cfg.storage.data_dir,
        webcam_index=cfg.camera.webcam_index or 0,
        process_fps=cfg.camera.process_fps,
        samples=samples,
    )


def cmd_aggregate(
    outlet_id: str,
    absent_seconds: int,
    data_dirs: list[str],
    spg_ids: list[str],
    poll: float,
    out_data_dir: str | None,
):
    from src.commands.run_outlet_aggregator import OutletAggregator

    agg = OutletAggregator(
        outlet_id=outlet_id,
        data_dirs=data_dirs,
        absent_seconds=absent_seconds,
        poll_interval_sec=poll,
        out_data_dir=out_data_dir,
    )
    agg.run(spg_ids)


def main():
    parser = argparse.ArgumentParser(prog="face_recog")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # debug
    p_debug = subparsers.add_parser("debug", help="Print config and preview webcam detector")
    p_debug.add_argument("--config", type=str, default=None)

    # run
    p_run = subparsers.add_parser("run", help="Run recognition worker (per camera)")
    p_run.add_argument("--config", type=str, default=None)

    # enroll
    p_enroll = subparsers.add_parser("enroll", help="Enroll person embeddings using webcam")
    p_enroll.add_argument("--config", type=str, default=None)
    p_enroll.add_argument("--spg_id", required=True)
    p_enroll.add_argument("--name", required=True)
    p_enroll.add_argument("--samples", type=int, default=30)

    # aggregate
    p_agg = subparsers.add_parser("aggregate", help="Run outlet aggregator (ANY-of-N cameras)")
    p_agg.add_argument("--outlet_id", required=True)
    p_agg.add_argument("--absent_seconds", type=int, default=300)
    p_agg.add_argument("--data_dirs", nargs="+", required=True)
    p_agg.add_argument("--spg_ids", nargs="+", required=True)
    p_agg.add_argument("--poll", type=float, default=1.0)
    p_agg.add_argument("--out_data_dir", type=str, default=None)

    args = parser.parse_args()

    if args.command == "debug":
        cmd_debug(args.config)
        return

    if args.command == "run":
        cmd_run(args.config)
        return

    if args.command == "enroll":
        cmd_enroll(args.config, args.spg_id, args.name, args.samples)
        return

    if args.command == "aggregate":
        cmd_aggregate(
            outlet_id=args.outlet_id,
            absent_seconds=args.absent_seconds,
            data_dirs=args.data_dirs,
            spg_ids=args.spg_ids,
            poll=args.poll,
            out_data_dir=args.out_data_dir,
        )
        return


if __name__ == "__main__":
    main()
