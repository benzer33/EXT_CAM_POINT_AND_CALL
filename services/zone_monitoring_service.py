"""
ZoneMonitoringService — QThread that runs No-Entry Zone detection.

Signals mirror MonitoringService for consistent UI wiring:
    frame_ready(QImage)
    stats_updated(dict)       keys: total, in_zone, fps
    intrusion_event(dict)     keys: track_id, zone_name, result, image_path, ts
    status_changed(str)
    error_occurred(str)
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import cv2
import numpy as np

from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
from PyQt5.QtGui  import QImage

from camera.camera_manager    import CameraManager
from detection.zone_detector  import ZoneDetector, Zone, zones_from_list


class ZoneMonitoringService(QThread):

    frame_ready     = pyqtSignal(QImage)
    stats_updated   = pyqtSignal(dict)
    intrusion_event = pyqtSignal(dict)
    status_changed  = pyqtSignal(str)
    error_occurred  = pyqtSignal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg     = cfg
        self._running = False
        self._mutex   = QMutex()
        self._zones:  list[Zone] = []
        self._counters = {"total": 0, "in_zone": 0}

        # load zones from config
        raw = cfg.get("zone_polygons", [])
        if raw:
            self._zones = zones_from_list(raw)

    # ── public API ────────────────────────────────────────────────────────────

    def set_zones(self, zones: list[Zone]):
        with QMutexLocker(self._mutex):
            self._zones = zones

    def get_zones(self) -> list[Zone]:
        return self._zones

    def stop(self):
        self._running = False

    def reset_counters(self):
        with QMutexLocker(self._mutex):
            self._counters = {"total": 0, "in_zone": 0}

    # ── thread entry ──────────────────────────────────────────────────────────

    def run(self):
        cfg         = self._cfg
        source      = cfg.get("camera_source", 0)
        save_images = cfg.get("save_images", True)
        capture_dir = cfg.get("capture_dir", "captures")
        saved_w     = cfg.get("zone_saved_w", 1280)
        saved_h     = cfg.get("zone_saved_h",  720)
        device      = cfg.get("device", "cpu")
        # Zone detection always uses a plain detection model, NOT the pose model.
        # If only a pose model is available (e.g. yolov8n-pose.pt) we fall back to
        # downloading/using yolov8n.pt automatically.
        det_model_path = cfg.get("zone_det_model", "yolov8n.pt")
        conf        = cfg.get("conf_threshold", 0.4)
        os.makedirs(capture_dir, exist_ok=True)

        self.status_changed.emit(f"Loading detection model {det_model_path}…")

        try:
            from ultralytics import YOLO
            model = YOLO(det_model_path)
        except Exception as e:
            self.error_occurred.emit(f"Model load failed: {e}")
            return

        # open camera
        camera = CameraManager()
        if not camera.connect(source):
            self.error_occurred.emit(f"Cannot open camera: {source}")
            return

        with QMutexLocker(self._mutex):
            detector = ZoneDetector(
                zones   = list(self._zones),
                saved_w = saved_w,
                saved_h = saved_h,
            )

        self.status_changed.emit("Zone monitoring started")
        self._running = True
        fps_counter   = _FPSCounter()
        counters      = self._counters
        mirror        = cfg.get("mirror_feed", False)
        # centroid tracker: maps stable_id -> last centroid (cx, cy)
        _next_id  = [0]
        _trackers: dict[int, tuple[float, float]] = {}   # id -> (cx, cy)
        _MAX_DIST = 80   # pixels: max centroid shift to count as same person

        while self._running:
            frame_raw = camera.read()
            if frame_raw is None:
                time.sleep(0.04)
                continue

            frame = cv2.flip(frame_raw, 1) if mirror else frame_raw.copy()
            fh, fw = frame.shape[:2]

            # sync zones in case they were updated
            with QMutexLocker(self._mutex):
                detector.set_zones(list(self._zones), saved_w, saved_h)

            # YOLO inference — person class only
            results = model(frame, conf=conf, classes=[0], verbose=False)[0]

            # Build raw bbox list from YOLO results
            raw_boxes: list[list[float]] = []
            if results.boxes is not None and len(results.boxes):
                raw_boxes = results.boxes.xyxy.cpu().numpy().tolist()

            # ── Centroid-based stable ID assignment ──────────────────────────
            # For each detected box, find the nearest existing tracker centroid.
            # If within _MAX_DIST reuse that ID; otherwise assign a new one.
            new_trackers: dict[int, tuple[float, float]] = {}
            detections: list[dict] = []
            used_ids: set[int] = set()

            for box in raw_boxes:
                x1, y1, x2, y2 = box
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2

                best_id   = None
                best_dist = _MAX_DIST + 1
                for tid, (ox, oy) in _trackers.items():
                    if tid in used_ids:
                        continue
                    d = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
                    if d < best_dist:
                        best_dist = d
                        best_id   = tid

                if best_id is not None:
                    stable_id = best_id
                else:
                    stable_id = _next_id[0]
                    _next_id[0] += 1

                used_ids.add(stable_id)
                new_trackers[stable_id] = (cx, cy)
                detections.append({"track_id": stable_id, "bbox": [x1, y1, x2, y2]})

            _trackers = new_trackers   # retire tracks that disappeared
            # ─────────────────────────────────────────────────────────────────

            # draw zones
            detector.draw_zones(frame, fw, fh)

            # check intrusions
            events = detector.check(detections, fw, fh)
            for ev in events:
                tid      = ev["track_id"]
                zname    = ev["zone_name"]
                bbox     = ev["bbox"]

                # highlight intruder
                detector.draw_intrusion_alert(frame, tid, bbox, zname)

                with QMutexLocker(self._mutex):
                    counters["total"] += 1

                img_path = ""
                if save_images:
                    img_path = _save_capture(frame, bbox, tid, "INTRUSION", capture_dir)

                self.intrusion_event.emit({
                    "track_id":  tid,
                    "zone_name": zname,
                    "result":    "INTRUSION",
                    "image_path": img_path,
                    "ts":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

            # draw person boxes
            for det in detections:
                x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 180, 255), 1)

            with QMutexLocker(self._mutex):
                counters["in_zone"] = detector.in_zone_count()

            fps = fps_counter.tick()
            _draw_hud(frame, fps)

            self.frame_ready.emit(_to_qimage(frame))
            self.stats_updated.emit({**counters, "fps": round(fps, 1)})

        camera.disconnect()
        self.status_changed.emit("Zone monitoring stopped")


# ── helpers ───────────────────────────────────────────────────────────────────

def _save_capture(frame, bbox, track_id: int, tag: str, capture_dir: str) -> str:
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        pad = 20
        h, w = frame.shape[:2]
        crop = frame[max(0, y1-pad):min(h, y2+pad),
                     max(0, x1-pad):min(w, x2+pad)]
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        name = f"{ts}_{tag}_id{track_id}.jpg"
        path = os.path.join(capture_dir, name)
        cv2.imwrite(path, crop)
        return path
    except Exception:
        return ""


def _draw_hud(frame, fps: float):
    h, w = frame.shape[:2]
    cv2.putText(frame, f"ZONE MONITOR  |  {fps:.1f} FPS",
                (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 140, 200), 1)


def _to_qimage(frame: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()


class _FPSCounter:
    def __init__(self):
        self._t   = time.time()
        self._fps = 0.0

    def tick(self) -> float:
        now = time.time()
        dt  = now - self._t
        self._t = now
        if dt > 0:
            self._fps = 0.8 * self._fps + 0.2 / dt
        return self._fps
