import cv2
import numpy as np
import time
import os

from src.storage.event_store import EventStore
from src.storage.snapshot_store import SnapshotStore
from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.face_detector import FaceDetector
from src.storage.gallery_store import GalleryStore
from src.pipeline.matcher import Matcher
from src.pipeline.presence_logic import PresenceEngine
from src.notification.telegram_notifier import TelegramNotifier
from src.pipeline.rtsp_reader import RTSPReader

from src.settings.logger import logger

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
    camera_source: str = "webcam",
    rtsp_url: str | None = None,
    preview: bool = True,
    loop_video: bool = False,
    gallery_dir: str | None = None,
    enable_notifier: bool = True,
    **kwargs,
):
    actual_gallery_dir = gallery_dir if gallery_dir else data_dir
    store = GalleryStore(actual_gallery_dir)
    gallery = store.load_all()

    event_store = EventStore(data_dir)
    snapshot_store = SnapshotStore(data_dir)

    notifier = None
    if enable_notifier:
        try:
            notifier = TelegramNotifier.from_env()
        except Exception as e:
            logger.warning(f"Telegram notifier disabled: {e}")

    matcher = Matcher(threshold=threshold)
    matcher.load_gallery(gallery)

    engine = PresenceEngine(
        outlet_id=outlet_id,
        camera_id=camera_id,
        grace_seconds=grace_seconds,
        absent_seconds=absent_seconds,
    )


    if camera_source == "webcam":
        reader = WebcamReader(webcam_index, process_fps)
    elif camera_source == "rtsp":
        if not rtsp_url:
            raise ValueError("rtsp_url must be provided for RTSP source")
        reader = RTSPReader(rtsp_url, process_fps)
        reader.set_loop(loop_video)
    else:
        raise ValueError(f"Unknown camera source: {camera_source}")

    detector = FaceDetector(
        name=kwargs.get("model_name", "buffalo_s"),
        providers=kwargs.get("execution_providers", None),
        det_size=tuple(kwargs.get("det_size", (640, 640)))
    )

    def handle_event(event, frame_for_snapshot=None):
        if event.event_type == "ABSENT_ALERT_FIRED" and frame_for_snapshot is not None:
            snap_path = snapshot_store.save_alert_frame(outlet_id, camera_id, frame_for_snapshot)
            event.details = dict(event.details or {})
            event.details["snapshot_path"] = snap_path

        event_store.append(event)
        logger.info(f"[EVENT] {event.event_type} - {event.spg_id}")

        if notifier is not None and event.event_type == "ABSENT_ALERT_FIRED":
            seconds = event.details.get("seconds_since_last_seen", "?")
            spg_name = event.name or event.spg_id
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event.ts))
            
            text = (
                f"⚠️ **SPG ABSENCE DETECTED** ⚠️\n\n"
                f"📍 **Outlet:** {event.outlet_id}\n"
                f"📷 **Camera:** {event.camera_id}\n"
                f"👤 **Personnel:** {spg_name} ({event.spg_id})\n"
                f"⏱️ **Duration:** {seconds}s\n"
                f"🕒 **Time:** {timestamp}\n"
            )

            snap = event.details.get("snapshot_path")
            try:
                if snap:
                    notifier.send_photo(snap, caption=text)
                else:
                    notifier.send_message(text)
            except Exception as ex:
                logger.error(f"Failed to send Telegram alert: {ex}")

    detector.start()
    reader.start()

    logger.info("Webcam recognition started. Press 'q' to quit.")
    logger.info(f"Gallery loaded: {len(gallery)} people  threshold={threshold}")

    last_snapshot_times = {}
    last_frame_time = 0
    # Path for latest camera frame (for dashboard preview)
    frame_path = os.path.join(data_dir, "snapshots", "latest_frame.jpg")

    try:
        while True:
            frame = reader.read_throttled()
            now = time.time()

            if frame is not None:
                faces = detector.detect(frame)

                seen_this_frame = set()

                for f in faces:
                    emb = getattr(f, "embedding", None)
                    matched, spg_id, name, sim = matcher.match(emb)

                    if not matched:
                        continue
                    if spg_id not in target_spg_ids:
                        continue
                    if spg_id in seen_this_frame:
                        continue

                    seen_this_frame.add(spg_id)
                    
                    # Throttled snapshot saving (max 1x per second)
                    last_save = last_snapshot_times.get(spg_id, 0)
                    if now - last_save > 1.0:
                        snapshot_store.save_latest_face(spg_id, frame)
                        last_snapshot_times[spg_id] = now

                    for e in engine.observe_seen(
                        spg_id=spg_id,
                        name=name,
                        similarity=sim,
                        ts=now,
                    ):
                        handle_event(e)

                    # draw bbox
                    x1, y1, x2, y2 = [int(v) for v in f.bbox]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    label = f"{name} ({sim:.2f})"
                    cv2.putText(
                        frame,
                        label,
                        (x1, max(0, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                    )

                # Save latest camera frame for dashboard preview (5x per second)
                if now - last_frame_time > 0.2:
                    try:
                        h, w = frame.shape[:2]
                        # Resize for dashboard (width 640)
                        small = cv2.resize(frame, (640, int(h * 640 / w)))
                        cv2.imwrite(frame_path, small, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        last_frame_time = now
                    except Exception:
                        pass

                # Only run local absence checks if NOT in multi-camera worker mode.
                # In multi-camera mode, the global OutletAggregator handles absence detection.
                if enable_notifier:
                    for e in engine.tick(target_spg_ids=target_spg_ids, ts=now):
                        if e.event_type == "ABSENT_ALERT_FIRED":
                            handle_event(e, frame_for_snapshot=frame)
                        else:
                            handle_event(e)

                if preview:
                    cv2.imshow(f"face_recog | {camera_id}", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    finally:
        reader.stop()
        cv2.destroyAllWindows()