"""
MonitoringService — QThread detection pipeline.
"""
from __future__ import annotations
import os, time, cv2, numpy as np
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
from PyQt5.QtGui  import QImage

from camera.camera_manager        import CameraManager
from detection.pose_detector      import PoseDetector
from detection.gesture_classifier import (
    classify_pose_gesture,
    draw_skeleton,
    draw_debug_kp,
)
from detection.person_state       import PersonState, GESTURE_ORDER, LOG_COOLDOWN
from detection.crossing_line      import CrossingLine
from detection.zone_detector      import Zone


class MonitoringService(QThread):
    frame_ready    = pyqtSignal(QImage)
    stats_updated  = pyqtSignal(dict)
    crossing_event = pyqtSignal(dict)
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg           = cfg
        self._running       = False
        self._mutex         = QMutex()
        self._crossing_line = CrossingLine()
        self._counters      = {"total": 0, "pass": 0, "fail": 0, "in_zone": 0}
        self._person_states: dict[int, PersonState] = {}
        # optional detection zone: only count people inside this polygon
        self._det_zone: list[tuple[int,int]] | None = None

        cl_cfg = cfg.get("crossing_line")
        if cl_cfg:
            self._crossing_line = CrossingLine.from_dict(cl_cfg)

    # ── public API ────────────────────────────────────────────────────────────
    def set_crossing_line(self, p1, p2):
        with QMutexLocker(self._mutex):
            self._crossing_line.set_points(p1, p2)

    def clear_crossing_line(self):
        with QMutexLocker(self._mutex):
            self._crossing_line.clear()

    def get_crossing_line(self) -> CrossingLine:
        return self._crossing_line

    def set_zone(self, points: list[tuple[int,int]], saved_w: int, saved_h: int):
        """Set a detection zone; only people inside will be counted."""
        with QMutexLocker(self._mutex):
            self._det_zone        = list(points)
            self._det_zone_saved_w = saved_w
            self._det_zone_saved_h = saved_h

    def clear_zone(self):
        """Remove the detection zone filter — count all visible people."""
        with QMutexLocker(self._mutex):
            self._det_zone = None

    def reset_counters(self):
        with QMutexLocker(self._mutex):
            self._counters = {"total": 0, "pass": 0, "fail": 0, "in_zone": 0}
            self._person_states.clear()

    def stop(self):
        self._running = False

    # ── thread entry ──────────────────────────────────────────────────────────
    def run(self):
        cfg          = self._cfg
        sensitivity  = cfg.get("sensitivity",   "STRICT")
        handsup_level = cfg.get("handsup_level", "waist")
        hold_sec     = cfg.get("hold_seconds", 0.3)
        save_images  = cfg.get("save_images", True)
        capture_dir  = cfg.get("capture_dir", "captures")
        log_cooldown = cfg.get("log_cooldown", 10.0)
        show_overlay   = cfg.get("show_debug_overlay", True)
        # infer_every_n: รัน YOLO inference ทุก n เฟรม, เฟรมที่เหลือ reuse ผลลัพธ์เก่า
        # ค่า default=2 หมายถึง inference 1 ใน 2 เฟรม (ลด CPU/GPU load ~50%)
        infer_every_n  = max(1, int(cfg.get("infer_every_n", 2)))
        os.makedirs(capture_dir, exist_ok=True)

        MIN_VISIBLE_FRAMES  = cfg.get("min_visible_frames",  8)
        MIN_BBOX_HEIGHT_REL = cfg.get("min_bbox_height_rel", 0.15)
        MIN_BBOX_WIDTH_REL  = cfg.get("min_bbox_width_rel",  0.05)

        device     = cfg.get("device", "cpu")
        model_path = cfg.get("yolo_model", "yolov8n-pose.pt")
        self.status_changed.emit(f"Loading {model_path} on {device}…")

        detector = None
        for attempt in ([device] if device == "cpu" else [device, "cpu"]):
            try:
                detector = PoseDetector(
                    model_path=model_path,
                    conf=cfg.get("conf_threshold", 0.5),
                    device=attempt,
                    track_activation_threshold=cfg.get("track_activation_threshold", 0.25),
                    lost_track_buffer=cfg.get("lost_track_buffer", 60),
                    minimum_matching_threshold=cfg.get("minimum_matching_threshold", 0.75),
                    frame_rate=cfg.get("tracker_frame_rate", 20),
                )
                if attempt != device:
                    self.status_changed.emit("⚠ GPU unavailable — running on CPU.")
                break
            except Exception as e:
                err = str(e)
                if attempt != "cpu" and ("1114" in err or "dll" in err.lower()):
                    self.status_changed.emit("GPU init failed, retrying on CPU…")
                    continue
                self.error_occurred.emit(f"Model load failed: {e}")
                return

        if detector is None:
            self.error_occurred.emit("Could not initialise detector.")
            return

        camera = CameraManager()
        source       = cfg.get("camera_source", 0)
        cam_target_w = cfg.get("camera_target_width",  1920)
        cam_target_h = cfg.get("camera_target_height", 1080)
        cam_codec    = cfg.get("camera_codec",         "h264")
        if not camera.connect(source, target_w=cam_target_w,
                               target_h=cam_target_h, codec=cam_codec):
            self.error_occurred.emit(f"Cannot open camera: {source}")
            return

        self.status_changed.emit("Monitoring started")
        self._running     = True
        fps_counter       = _FPSCounter()
        person_states     = self._person_states
        counters          = self._counters
        mirror            = cfg.get("mirror_feed", False)
        frame_idx         = 0          # นับเฟรมที่อ่านมาสำเร็จ
        _last_det_result  = None       # DetectionResult จาก inference ครั้งล่าสุด
        # ── grace period / re-ID ─────────────────────────────────────────────
        pending_exits: dict = {}       # track_id -> {"state", "gone_since", "bbox"}
        GRACE_PERIOD_SEC  = cfg.get("track_grace_period_sec",      1.5)
        REID_MAX_DISTANCE = cfg.get("track_reid_max_distance_px", 150)

        while self._running:
            frame_raw = camera.read()
            if frame_raw is None:
                time.sleep(0.05)
                continue

            frame_idx    += 1
            run_inference = (frame_idx % infer_every_n == 0)

            if run_inference:
                # รัน YOLO inference เต็มๆ และเก็บผลลัพธ์ไว้ reuse
                frame_mirror, det_result = detector.process(frame_raw, mirror=mirror)
                _last_det_result = det_result
            else:
                # ข้าม inference — flip/copy frame ให้ GUI ไม่ค้าง แต่ใช้ผล detection เก่า
                import cv2 as _cv2
                frame_mirror = _cv2.flip(frame_raw, 1) if mirror else frame_raw.copy()
                det_result   = _last_det_result

            # ถ้ายังไม่มีผล inference เลย (เฟรมแรกๆ ที่ skip) ให้รอรอบถัดไป
            if det_result is None:
                self.frame_ready.emit(_to_qimage(frame_mirror))
                continue

            fh, fw = frame_mirror.shape[:2]

            with QMutexLocker(self._mutex):
                crossing_line = self._crossing_line

            active_ids = set()

            # read zone snapshot once per frame
            with QMutexLocker(self._mutex):
                det_zone        = self._det_zone
                det_zone_saved_w = getattr(self, "_det_zone_saved_w", fw)
                det_zone_saved_h = getattr(self, "_det_zone_saved_h", fh)

            for person in det_result.persons:
                track_id = person.track_id
                bbox     = person.bbox
                kps      = person.keypoints

                # if a detection zone is active, skip people outside it
                if det_zone and len(det_zone) >= 3:
                    z = Zone("det", det_zone)
                    scaled = z.scale_to(det_zone_saved_w, det_zone_saved_h, fw, fh)
                    if scaled.sample_points_inside(list(bbox)) < 1:
                        _draw_person(frame_mirror, person, person_states.get(
                            track_id, type("_", (), {"track_id": track_id,
                            "passed_for_mode": lambda *a: False,
                            "completed": set(), "frames_seen": 0})()), None, sensitivity, False)
                        continue

                active_ids.add(track_id)

                if track_id not in person_states:
                    matched_gid = _find_matching_pending_exit(
                        bbox, pending_exits, GRACE_PERIOD_SEC, REID_MAX_DISTANCE
                    )
                    if matched_gid is not None:
                        recovered = pending_exits.pop(matched_gid)
                        state = recovered["state"]
                        state.track_id = track_id
                        person_states[track_id] = state
                    else:
                        person_states[track_id] = PersonState(track_id=track_id)
                state = person_states[track_id]
                state.frames_seen += 1
                state._last_bbox = bbox   # keep latest bbox for gone-handler capture

                # bbox size guard
                bbox_w = bbox[2] - bbox[0]
                bbox_h = bbox[3] - bbox[1]
                is_full = (bbox_h >= fh * MIN_BBOX_HEIGHT_REL and
                           bbox_w >= fw * MIN_BBOX_WIDTH_REL)
                if not is_full:
                    _draw_person(frame_mirror, person, state, None, sensitivity, show_overlay)
                    continue

                gesture = classify_pose_gesture(kps, sensitivity, handsup_level) if kps is not None else None

                if gesture and state.accept_gesture(gesture, sensitivity):
                    now = time.time()
                    if gesture not in state.gesture_start:
                        state.gesture_start[gesture] = now
                    elapsed = now - state.gesture_start[gesture]
                    if elapsed >= hold_sec:
                        state.completed.add(gesture)
                        state.gesture_start.pop(gesture, None)
                        # เพิ่ม next_expected สำหรับทุก mode ที่ใช้ ordered sequence
                        if sensitivity in ("STRICT", "HANDSUP"):
                            state.next_expected += 1
                    for g in list(state.gesture_start):
                        if g != gesture:
                            state.gesture_start.pop(g)
                else:
                    # gesture is None OR gesture not accepted (wrong order/already done)
                    # matches prototype: clear pending timer when not holding a valid pose
                    state.gesture_start.clear()

                if crossing_line.active:
                    foot_x   = (bbox[0] + bbox[2]) / 2
                    foot_y   = bbox[3]
                    cur_side = crossing_line.side(foot_x, foot_y)

                    if state.last_side == 0:
                        state.last_side = cur_side
                    elif cur_side != state.last_side:
                        state.last_side = cur_side
                        if state.frames_seen >= MIN_VISIBLE_FRAMES and state.can_log(log_cooldown):
                            state.crossed = True
                            result = "PASS" if state.passed_for_mode(sensitivity) else "FAIL"
                            with QMutexLocker(self._mutex):
                                counters["total"] += 1
                                counters["pass" if result == "PASS" else "fail"] += 1
                            img_path = ""
                            if save_images:
                                img_path = _save_capture(frame_mirror, bbox, track_id,
                                                         result, capture_dir)
                            state.last_log_time = time.time()
                            self.crossing_event.emit({
                                "track_id":   track_id,
                                "result":     result,
                                "mode":       sensitivity,
                                "image_path": img_path,
                                "ts":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            })
                            # reset checklist for next pass — only after a valid count
                            state.completed.clear()
                            state.gesture_start.clear()
                            state.next_expected = 0

                _draw_person(frame_mirror, person, state, gesture, sensitivity, show_overlay)

            gone = set(person_states.keys()) - active_ids
            for gid in gone:
                st = person_states.pop(gid)
                pending_exits[gid] = {
                    "state":      st,
                    "gone_since": time.time(),
                    "bbox":       getattr(st, "_last_bbox", None),
                }

            # flush expired pending_exits — คนที่หายเกิน grace period = เดินออกจริง
            expired_gids = [
                gid for gid, info in pending_exits.items()
                if time.time() - info["gone_since"] > GRACE_PERIOD_SEC
            ]
            for gid in expired_gids:
                info = pending_exits.pop(gid)
                st   = info["state"]
                if not st.crossed and st.frames_seen >= MIN_VISIBLE_FRAMES:
                    result = "PASS" if st.passed_for_mode(sensitivity) else "FAIL"
                    with QMutexLocker(self._mutex):
                        counters["total"] += 1
                        counters["pass" if result == "PASS" else "fail"] += 1
                    img_path = ""
                    if save_images and info["bbox"] is not None:
                        img_path = _save_capture(frame_mirror, info["bbox"],
                                                 gid, result, capture_dir)
                    self.crossing_event.emit({
                        "track_id":   gid,
                        "result":     result,
                        "mode":       sensitivity,
                        "image_path": img_path,
                        "ts":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })

            with QMutexLocker(self._mutex):
                counters["in_zone"] = len(active_ids)

            if crossing_line.active:
                _draw_crossing_line(frame_mirror, crossing_line)

            # draw detection zone overlay if active
            if det_zone and len(det_zone) >= 3:
                z = Zone("det", det_zone)
                scaled = z.scale_to(det_zone_saved_w, det_zone_saved_h, fw, fh)
                pts = scaled.np_points
                overlay = frame_mirror.copy()
                cv2.fillPoly(overlay, [pts], (0, 180, 80))
                cv2.addWeighted(overlay, 0.15, frame_mirror, 0.85, 0, frame_mirror)
                cv2.polylines(frame_mirror, [pts], True, (0, 220, 80), 2)

            fps = fps_counter.tick()
            _draw_hud(frame_mirror, sensitivity, fps)

            self.frame_ready.emit(_to_qimage(frame_mirror))
            self.stats_updated.emit({**counters, "fps": round(fps, 1)})

        camera.disconnect()
        self.status_changed.emit("Monitoring stopped")


# ── helpers ───────────────────────────────────────────────────────────────────

GESTURE_ICONS  = {"LEFT": "L", "RIGHT": "R", "STRAIGHT": "S", "HANDSUP": "H"}
GESTURE_LABELS = {"LEFT": "<- LEFT", "RIGHT": "RIGHT ->", "STRAIGHT": "^ STRAIGHT", "HANDSUP": "^ HANDS UP"}
GESTURE_LABELS = {"LEFT": "<- LEFT", "RIGHT": "RIGHT ->", "STRAIGHT": "^ STRAIGHT"}
COLOR_PASS = (0,  200,  80)
COLOR_WARN = (0,  140, 255)
COLOR_BLK  = (0,    0,   0)
COLOR_CYAN = (255, 220,  0)


def _draw_person(frame, person, state, gesture, sensitivity, show_overlay: bool = True):
    """
    Draw bbox, checklist label, gesture annotation, skeleton and optional debug overlay.
    Matches prototype draw_person_label + draw_skeleton + draw_debug_kp exactly.
    """
    from detection.person_state import GESTURE_ORDER
    bbox = person.bbox
    kps  = person.keypoints
    x1, y1, x2, y2 = [int(v) for v in bbox]

    passed     = state.passed_for_mode(sensitivity)
    box_color  = COLOR_PASS if passed else COLOR_WARN

    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

    # ── checklist label ───────────────────────────────────────────────────────
    from detection.person_state import HANDSUP_ORDER
    if sensitivity == "LOOSE":
        show_gestures = ["LEFT", "RIGHT"]
    elif sensitivity == "HANDSUP":
        show_gestures = HANDSUP_ORDER
    else:
        show_gestures = GESTURE_ORDER
    checks = "".join(
        f"[{GESTURE_ICONS[g]}]" if g in state.completed else f"({GESTURE_ICONS[g]})"
        for g in show_gestures
    )
    status = "PASS" if passed else checks
    label  = f"#{state.track_id}  {status}"
    lw, lh = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
    cv2.rectangle(frame, (x1, y1 - lh - 8), (x1 + lw + 6, y1), box_color, -1)
    cv2.putText(frame, label, (x1 + 3, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_BLK, 2, cv2.LINE_AA)

    # ── current gesture annotation ────────────────────────────────────────────
    if gesture and not passed:
        cv2.putText(frame, GESTURE_LABELS.get(gesture, gesture), (x1, y2 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_CYAN, 2, cv2.LINE_AA)

    # ── skeleton + debug overlay ──────────────────────────────────────────────
    if kps is not None:
        skel_color = COLOR_PASS if passed else (80, 180, 255)
        draw_skeleton(frame, kps, skel_color)
        if show_overlay:
            draw_debug_kp(frame, kps, bbox)



def _draw_crossing_line(frame, line: CrossingLine):
    p1 = (int(line.p1[0]), int(line.p1[1]))
    p2 = (int(line.p2[0]), int(line.p2[1]))
    cv2.line(frame, p1, p2, (0, 220, 255), 2)
    cv2.circle(frame, p1, 5, (0, 220, 255), -1)
    cv2.circle(frame, p2, 5, (0, 220, 255), -1)


def _draw_hud(frame, sensitivity: str, fps: float):
    h, w = frame.shape[:2]
    txt  = f"{sensitivity}  |  {fps:.1f} FPS"
    cv2.putText(frame, txt, (10, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 140, 200), 1)


def _save_capture(frame, bbox, track_id: int, result: str, capture_dir: str) -> str:
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        pad = 20
        h, w = frame.shape[:2]
        crop = frame[max(0, y1-pad):min(h, y2+pad), max(0, x1-pad):min(w, x2+pad)]
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        name = f"{ts}_{result}_id{track_id}.jpg"
        path = os.path.join(capture_dir, name)
        cv2.imwrite(path, crop)
        return path
    except Exception:
        return ""


def _find_matching_pending_exit(bbox, pending_exits: dict,
                                 grace_period: float,
                                 max_distance: float) -> "int | None":
    """
    หา pending_exits ที่ตำแหน่ง bbox ใกล้เคียงกับ bbox ที่หายไปล่าสุด และยังอยู่ใน
    grace period  คืนค่า track_id (key) ที่ใกล้สุดและผ่านเงื่อนไข  ไม่เจอคืน None
    """
    now  = time.time()
    cx   = (bbox[0] + bbox[2]) / 2
    cy   = (bbox[1] + bbox[3]) / 2
    best_gid  = None
    best_dist = max_distance
    expired   = []
    for gid, info in pending_exits.items():
        if now - info["gone_since"] > grace_period:
            expired.append(gid)
            continue
        old_bbox = info["bbox"]
        if old_bbox is None:
            continue
        ox = (old_bbox[0] + old_bbox[2]) / 2
        oy = (old_bbox[1] + old_bbox[3]) / 2
        dist = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_gid  = gid
    for gid in expired:
        pending_exits.pop(gid, None)
    return best_gid


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
            self._fps = 0.8 * self._fps + 0.2 * (1.0 / dt)
        return self._fps
