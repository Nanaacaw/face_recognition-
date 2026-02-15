import argparse
from src.settings.settings import load_settings

import cv2
from src.settings.settings import load_settings
from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.face_detector import FaceDetector

def cmd_debug():
    cfg = load_settings()
    print("=== face_recog DEBUG MODE ===")
    print(cfg)

    print("ONNX providers:", ort.get_available_providers())

    if not cfg.camera.preview:
        print("preview=false, only printing config.")
        return

    if cfg.camera.source != "webcam":
        print("debug preview currently supports webcam only.")
        return

    reader = WebcamReader(
        index=cfg.camera.webcam_index or 0,
        process_fps=cfg.camera.process_fps,
    )

    detector = FaceDetector(det_size=(640, 640))

    reader.start()
    detector.start()
    print("Webcam preview started. Press 'q' to quit.")

    try:
        while True:
            frame = reader.read_throttled()

            if frame is None:
            
                faces = detector.detect(frame)

                for f in faces:
                    x1, y1, x2, y2 = [int(v) for v in f.bbox]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    score = getattr(f, "det_score", 0.0)
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
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    finally:
        reader.stop()



def main():
    parser = argparse.ArgumentParser(prog="face_recog")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("debug")

    subparsers.add_parser("run")

    enroll_p = subparsers.add_parser("enroll")
    enroll_p.add_argument("--spg_id", required=True)
    enroll_p.add_argument("--name", required=True)
    enroll_p.add_argument("--samples", type=int, default=30)

    args = parser.parse_args()

    if args.command == "debug":
        cmd_debug()

    elif args.command == "run":
        cfg = load_settings()
        from src.commands.run_webcam import run_webcam_recognition

        if cfg.camera.source != "webcam":
            print("run currently supports webcam only.")
            return

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
        )

    elif args.command == "enroll":
        from src.enrollment.enroll_webcam import enroll_from_webcam
        cfg = load_settings()

        enroll_from_webcam(
            spg_id=args.spg_id,
            name=args.name,
            data_dir=cfg.storage.data_dir,
            webcam_index=cfg.camera.webcam_index or 0,
            process_fps=cfg.camera.process_fps,
            samples=args.samples,
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
