import cv2
import numpy as np
import time

from src.storage.event_store import EventStore
from src.storage.snapshot_store import SnapshotStore
from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.face_detector import FaceDetector
from src.storage.gallery_store import GalleryStore
from src.pipeline.matcher import Matcher
from src.pipeline.presence_logic import PresenceEngine
from src.notification.telegram_notifier import TelegramNotifier

def run_webcam_recognition(
    data_dir: str,
    webcam_index: int,
    process_fps: int,
    threshold: float,
    grace_seconds: int,
    absent_seconds: int,
    outlet_id: str,
    camera_id: str,
    target_spg_ids: list[str],
):
    store = GalleryStore(data_dir)
    gallery = store.load_all()

    event_store = EventStore(data_dir)
    snapshot_store = SnapshotStore(data_dir)

    notifier = None
    try:
        notifier = TelegramNotifier.from_env()
    except Exception as e:
        print("[WARN] Telegram notifier disabled:", e)

    matcher = Matcher(threshold=threshold)
    matcher.load_gallery(gallery)

    engine = PresenceEngine(
        outlet_id=outlet_id,
        camera_id=camera_id,
        grace_seconds=grace_seconds,
        absent_seconds=absent_seconds,
    )

    reader = WebcamReader(webcam_index, process_fps)
    detector = FaceDetector(det_size=(640, 640))

    def handle_event(event, frame_for_snapshot=None):
        if e.event_type == "ABSENT_ALERT_FIRED" and frame_for_snapshot is not None:
            snap_path = snapshot_store.save_alert_frame(outlet_id, camera_id, frame_for_snapshot)
            e.details = dict(e.details or {})
            e.details["snapshot_path"] = snap_path

        event_store.append(e)
        print("[EVENT]", e.model_dump())

        if notifier is not None and event.event_type == "ABSENT_ALERT_FIRED":
            seconds = event.details.get("seconds_since_last_seen")
            text = (
                f"⚠️ SPG ABSENT ALERT\n"
                f"Outlet: {event.outlet_id}\n"
                f"Camera: {event.camera_id}\n"
                f"SPG: {event.name or event.spg_id}\n"
                f"Last seen: {seconds}s ago"
            )

            snap = event.details.get("snapshot_path")
            try:
                if snap:
                    notifier.send_photo(snap, caption=text)
                else:
                    notifier.send_message(text)
            except Exception as ex:
                print("[ERROR] Failed to send Telegram alert:", ex)

    detector.start()
    reader.start()

    print("[RUN] Webcam recognition started. Press 'q' to quit.")
    print(f"[RUN] Gallery loaded: {list(gallery.keys())}  threshold={threshold}")


    try:
        while True:
            frame = reader.read_throttled()

            if frame is not None:
                faces = detector.detect(frame)

                # pick best face (highest det_score)
                best = None
                best_score = -1.0

                for f in faces:
                    score = float(getattr(f, "det_score", 0.0))
                    if score > best_score:
                        best_score = score
                        best = f
                
                now = time.time()

                if best is not None:
                    x1, y1, x2, y2 = [int(v) for v in best.bbox]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    emb = getattr(best, "embedding", None)
                    matched, spg_id, name, sim = matcher.match(emb)

                    if matched and spg_id in target_spg_ids:
                        for e in engine.observe_seen(
                            spg_id = spg_id,
                            name = name,
                            similarity = sim,
                            ts = now
                        ):
                            handle_event(e)

                    if matched:
                        label = f"{name} ({sim:.2f})"
                        color = (0, 255, 0)
                    else:
                        label = f"UNKNOWN ({sim:.2f})"
                        color = (0, 0, 255)
                                         
                    cv2.putText(
                        frame,
                        label,
                        (x1, max(0, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        color,
                        2,
                    )

                for e in engine.tick(target_spg_ids=target_spg_ids, ts=now):
                    if e.event_type == "ABSENT_ALERT_FIRED":
                        handle_event(e, frame_for_snapshot=frame)
                    else:
                        handle_event(e)

                cv2.imshow("face_recog | run", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    finally:
        reader.stop()
        cv2.destroyAllWindows()