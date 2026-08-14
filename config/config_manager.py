"""
ConfigManager — load/save application config and named profiles.
"""

from __future__ import annotations
import json
import os

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG: dict = {
    "camera_source":        "rtsp://admin:รหัสจริง@192.168.250.58:554/Streaming/Channels/102",
    "camera_target_width":  1028,   # ความกว้าง output ที่ decode มา (GStreamer NVDEC)
    "camera_target_height": 720,   # ความสูง output ที่ decode มา (GStreamer NVDEC)
    "camera_codec":         "h265", # "h264" หรือ "h265" — ต้องตรงกับ codec จริงของกล้อง
    "yolo_model":           "yolov8n-pose.pt",
    "conf_threshold":       0.5,
    # ── ByteTrack tracker parameters ─────────────────────────────────────────
    "track_activation_threshold":   0.25,  # confidence ขั้นต่ำในการสร้าง track ใหม่
    "lost_track_buffer":            60,    # frame ที่จำ track ก่อนลบ (สูง = ทนทาน occlusion)
    "minimum_matching_threshold":   0.75,  # IoU threshold จับคู่ detection กับ track
    "tracker_frame_rate":           20,    # FPS ของ stream (ใช้คำนวณ buffer ภายใน ByteTrack)
    # ── Re-ID grace period (ป้องกัน track switching log ผิด) ─────────────────
    "track_grace_period_sec":       1.5,   # วินาทีรอก่อน log ว่าคนเดินออกจริง
    "track_reid_max_distance_px":   150,   # px สูงสุดในการจับคู่ track เก่า-ใหม่
    "hold_seconds":         0.3,
    "sensitivity":          "STRICT",
    "handsup_level":         "waist",   # "waist" | "chest" | "shoulder" — ระดับเกณฑ์โหมด HANDSUP
    "require_face_to_log":        False,     # True = นับ PASS/FAIL เฉพาะตอนเจอหน้าคน | False = นับทุกกรณีเหมือนเดิม
    "require_direction_gate":     False,     # เปิด/ปิด — เช็คทิศทางการเดินก่อนนับ PASS/FAIL
    "direction_from_side":        -1,        # ฝั่งเริ่มต้นที่ต้องมี (1 หรือ -1 ตาม CrossingLine.side())
    "direction_to_side":           1,        # ฝั่งปลายทางที่ต้องไปถึง
    "gate1_first":                 True,     # True = ต้องผ่าน edge[0]-[1] ก่อน edge[2]-[3] ถึงนับว่าถูกทิศทาง
    "gate2_entering_side": 1,   # ใส่ค่าจริงที่เจอจากขั้นที่ 1 (ตัวอย่าง -1)
    "enable_forklift_suppression": False,   # เปิด/ปิด feature (default ปิด)
    "forklift_model_path":         "models/forklift_best.pt",
    "forklift_conf_threshold":     0.4,
    "forklift_infer_every_n":      5,       # รันโมเดลโฟล์คลิฟท์ทุก N เฟรม (เบากว่า pose)
    "forklift_overlap_ratio":      0.5,     # สัดส่วนทับซ้อนขั้นต่ำที่นับว่า "อยู่ในรถ"
    "min_forklift_frames":         3,       # ต้องเจอต่อเนื่องกี่เฟรมก่อนเชื่อว่าจริง
    "device":               "0",
    "save_images":          True,
    "save_images_on_pass":  False,   # ไม่เก็บภาพตอน PASS (ประหยัดพื้นที่)
    "save_images_on_fail":  True,    # เก็บภาพตอน FAIL (ใช้เป็นหลักฐาน)
    "capture_full_frame":   True,    # True = เต็มเฟรม (เห็นบริบท), False = crop เฉพาะคน (แบบเดิม)
    "save_video_on_fail":   True,
    "video_buffer_seconds": 3,
    "video_buffer_fps":     10,
    "video_output_dir":     "",   # ว่าง = ใช้ capture_dir/videos
    "retention_days":       30,
    "capture_dir":          os.path.join(BASE_DIR, "captures"),
    "save_raw_training_frame": True,
    "raw_capture_dir":      "",
    "crossing_line":        None,
    "teams_webhook":        "",
    "teams_send_pass":      False,
    "teams_send_fail":      True,
    "auto_load_profile":    "",
    "auto_connect":         False,
    "auto_start":           False,
    "theme":                "dark",
    "language":             "en",
    "show_debug_overlay":   True,   # show shoulder line + wrist dots
    "mirror_feed":          False,  # flip frame horizontally (True for webcam, False for IP cam)
    # ── gesture thresholds — must match prototype values ────────────────────
    "side_ratio":           0.05,   # POINT_SIDE_RATIO
    "height_ratio":         0.40,   # POINT_HEIGHT_RATIO
    "straight_ratio":       0.01,   # STRAIGHT_RATIO
    "center_ratio":         0.45,   # CENTER_RATIO
    "min_visible_frames":   8,
    "min_bbox_height_rel":  0.15,
    "min_bbox_width_rel":   0.05,
    "log_cooldown":         10.0,
    # ── No-Entry Zone ────────────────────────────────────────────────────────
    "zone_polygons":        [],    # list of Zone dicts (see detection/zone_detector.py)
    "zone_saved_w":         1280,  # canvas resolution when zones were drawn
    "zone_saved_h":          720,
    "zone_det_model":       "yolov8n.pt",   # plain detection model for zone service
    # ── Dashboard Detection Zone ────────────────────────────────────────────────
    "dashboard_zone":       [],    # list of [x,y] points for the dashboard filter zone
    "dashboard_zone_w":     1280,  # canvas resolution when dashboard zone was drawn
    "dashboard_zone_h":      720,
    # ── SQLite local database ────────────────────────────────────────────────
    "sqlite_path":          os.path.join(BASE_DIR, "captures", "events.db"),
    # ── RTSP Profiles (scanner) ──────────────────────────────────────────────
    "rtsp_profiles":        [],    # [{"name":…, "ip":…, "url":…}]
    "rtsp_credentials":     [      # tried in order by scanner
        {"username": "admin", "password": "REDACTED_CAMERA_PASSWORD"},
        {"username": "admin", "password": "REDACTED_CAMERA_PASSWORD"},
    ],
    "mssql": {
        "server":   "",
        "database": "",
        "username": "",
        "password": "",
        "driver":   "ODBC Driver 17 for SQL Server",
    },
}


class ConfigManager:
    """Handles loading, saving, and merging application config."""

    def __init__(self, config_file: str = CONFIG_FILE):
        self._path = config_file
        self._data = DEFAULT_CONFIG.copy()

    def load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    on_disk = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                if "mssql" in on_disk:
                    merged["mssql"] = {**DEFAULT_CONFIG["mssql"], **on_disk.pop("mssql")}
                merged.update(on_disk)
                self._data = merged
            except Exception as e:
                print(f"[Config] Load failed ({e}), using defaults")
        self._data = self._data
        return self._data

    def save(self, data: dict | None = None):
        if data is not None:
            self._data = data
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Save failed: {e}")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    @property
    def data(self) -> dict:
        return self._data
