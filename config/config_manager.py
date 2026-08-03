"""
ConfigManager — load/save application config and named profiles.
"""

from __future__ import annotations
import json
import os

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG: dict = {
    "camera_source":        0,
    "yolo_model":           "yolov8n-pose.pt",
    "conf_threshold":       0.5,
    "hold_seconds":         0.3,
    "sensitivity":          "STRICT",
    "device":               "cpu",
    "save_images":          True,
    "retention_days":       30,
    "capture_dir":          os.path.join(BASE_DIR, "captures"),
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
