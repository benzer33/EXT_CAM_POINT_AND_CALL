"""
ZoneDetector — polygon-based No-Entry Zone detection.

A zone is a named polygon stored as a list of (x, y) pixel points
(relative to the camera resolution at save time).  The detector checks
whether a person's bounding-box centre or foot-point falls inside any
active zone and fires an intrusion event with cooldown.
"""
from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
import cv2
import numpy as np


# ── Zone data class ───────────────────────────────────────────────────────────

@dataclass
class Zone:
    name:       str
    points:     list[tuple[int, int]]   # polygon vertices in pixel coords
    color:      tuple[int, int, int] = (0, 60, 220)   # BGR
    enabled:    bool = True
    alert_text: str  = "INTRUSION"

    def to_dict(self) -> dict:
        return {
            "name":       self.name,
            "points":     [[p[0], p[1]] for p in self.points],
            "color":      list(self.color),
            "enabled":    self.enabled,
            "alert_text": self.alert_text,
        }

    @staticmethod
    def from_dict(d: dict) -> "Zone":
        return Zone(
            name       = d.get("name", "Zone"),
            points     = [tuple(p) for p in d.get("points", [])],
            color      = tuple(d.get("color", [0, 60, 220])),
            enabled    = d.get("enabled", True),
            alert_text = d.get("alert_text", "INTRUSION"),
        )

    @property
    def np_points(self) -> np.ndarray:
        """Return Nx1x2 int32 array for cv2 polygon functions."""
        return np.array(self.points, dtype=np.int32).reshape((-1, 1, 2))

    def contains(self, x: float, y: float) -> bool:
        """Return True if point (x,y) is inside this polygon."""
        if len(self.points) < 3:
            return False
        return cv2.pointPolygonTest(self.np_points, (float(x), float(y)), False) >= 0

    def sample_points_inside(self, bbox: list) -> int:
        """Count how many representative points of a bbox fall inside the polygon.

        Samples: centroid, foot-center, head-center, and the 4 quarter points
        of the box.  Returns the number of sampled points inside (0..7).
        """
        if len(self.points) < 3:
            return 0
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        samples = [
            (cx,            (y1 + y2) / 2),   # centroid
            (cx,            y2),              # foot center
            (cx,            y1 + (y2 - y1) * 0.15),  # head-ish
            (cx,            y1 + (y2 - y1) * 0.66),  # lower torso
            ((x1 + cx) / 2, (y1 + y2) / 2),   # left-mid
            ((cx + x2) / 2, (y1 + y2) / 2),   # right-mid
            (cx,            y1 + (y2 - y1) * 0.40),  # upper torso
        ]
        cnt = 0
        pts = self.np_points
        for (sx, sy) in samples:
            if cv2.pointPolygonTest(pts, (float(sx), float(sy)), False) >= 0:
                cnt += 1
        return cnt

    def scale_to(self, src_w: int, src_h: int, dst_w: int, dst_h: int) -> "Zone":
        """Return a new Zone with points scaled from (src_w,src_h) to (dst_w,dst_h)."""
        sx = dst_w / src_w if src_w else 1.0
        sy = dst_h / src_h if src_h else 1.0
        new_pts = [(int(p[0] * sx), int(p[1] * sy)) for p in self.points]
        return Zone(self.name, new_pts, self.color, self.enabled, self.alert_text)


# ── Per-person intrusion state ────────────────────────────────────────────────

@dataclass
class IntrusionState:
    track_id:      int
    last_log_time: float = 0.0
    frames_inside: int   = 0    # continuous frames detected inside zone

    def can_log(self, cooldown: float = 10.0) -> bool:
        return (time.time() - self.last_log_time) >= cooldown


# ── Zone detector ─────────────────────────────────────────────────────────────

class ZoneDetector:
    """
    Manages a list of Zone polygons and checks detections against them.

    Usage:
        zd = ZoneDetector(zones)
        events = zd.check(detections, frame_w, frame_h)
        # events: list of (track_id, zone_name, foot_x, foot_y)
    """

    TRIGGER_FRAMES = 2      # must be inside zone for this many consecutive frames
    LOG_COOLDOWN   = 10.0   # seconds before re-logging same track in same zone
    MIN_POINTS_IN  = 2      # min sampled bbox points (of 7) inside polygon → "in zone"

    def __init__(self, zones: list[Zone] | None = None,
                 saved_w: int = 1280, saved_h: int = 720):
        self._zones:   list[Zone]                     = zones or []
        self._saved_w: int                            = saved_w
        self._saved_h: int                            = saved_h
        # (track_id, zone_name) → IntrusionState
        self._states:  dict[tuple, IntrusionState]    = {}
        # track_ids currently inside ANY active zone (refreshed every check())
        self._currently_inside: set[int]              = set()

    # ── zone management ───────────────────────────────────────────────────────

    def _zone_signature(self, zones: list[Zone]) -> tuple:
        """A hashable fingerprint of the current zone geometry/enabled state."""
        return tuple(
            (z.name, z.enabled, tuple(z.points)) for z in zones
        )

    def set_zones(self, zones: list[Zone], saved_w: int = 1280, saved_h: int = 720):
        # Only reset per-person intrusion state when the zones actually change.
        # This method is called every frame, so blindly clearing state would
        # keep frames_inside at 0 and no intrusion would ever trigger.
        new_sig = self._zone_signature(zones)
        changed = (
            new_sig != self._zone_signature(self._zones)
            or saved_w != self._saved_w
            or saved_h != self._saved_h
        )
        self._zones   = zones
        self._saved_w = saved_w
        self._saved_h = saved_h
        if changed:
            self._states.clear()
            self._currently_inside.clear()

    def get_zones(self) -> list[Zone]:
        return self._zones

    def in_zone_count(self) -> int:
        """Number of distinct tracks currently inside any active zone."""
        return len(self._currently_inside)

    # ── detection ─────────────────────────────────────────────────────────────

    def check(
        self,
        detections: list[dict],   # each: {"track_id": int, "bbox": [x1,y1,x2,y2]}
        frame_w: int,
        frame_h: int,
    ) -> list[dict]:
        """
        Check detections against all active zones.
        Returns list of intrusion event dicts:
          {"track_id", "zone_name", "foot_x", "foot_y", "bbox"}
        """
        events: list[dict] = []
        active_keys: set[tuple] = set()
        self._currently_inside = set()

        # pre-scale each enabled polygon once for this frame
        scaled_zones = [
            (z, z.scale_to(self._saved_w, self._saved_h, frame_w, frame_h))
            for z in self._zones if z.enabled and len(z.points) >= 3
        ]

        for det in detections:
            tid  = det["track_id"]
            bbox = det["bbox"]
            foot_x = (bbox[0] + bbox[2]) / 2
            foot_y = bbox[3]

            for zone, scaled in scaled_zones:
                key = (tid, zone.name)
                active_keys.add(key)

                # a person is "inside" when enough sampled bbox points hit the polygon
                inside = scaled.sample_points_inside(bbox) >= self.MIN_POINTS_IN

                if inside:
                    self._currently_inside.add(tid)
                    if key not in self._states:
                        self._states[key] = IntrusionState(track_id=tid)
                    st = self._states[key]
                    st.frames_inside += 1

                    if (st.frames_inside >= self.TRIGGER_FRAMES
                            and st.can_log(self.LOG_COOLDOWN)):
                        st.last_log_time = time.time()
                        events.append({
                            "track_id":  tid,
                            "zone_name": zone.name,
                            "foot_x":    foot_x,
                            "foot_y":    foot_y,
                            "bbox":      bbox,
                        })
                else:
                    # outside zone — reset continuous counter
                    if key in self._states:
                        self._states[key].frames_inside = 0

        # remove states for tracks that disappeared
        stale = [k for k in self._states if k not in active_keys]
        for k in stale:
            del self._states[k]

        return events

    # ── drawing ───────────────────────────────────────────────────────────────

    def draw_zones(self, frame: np.ndarray, frame_w: int, frame_h: int):
        """Draw all zones on frame (scaled to current resolution)."""
        for zone in self._zones:
            if not zone.enabled or len(zone.points) < 2:
                continue
            scaled = zone.scale_to(self._saved_w, self._saved_h, frame_w, frame_h)
            pts    = scaled.np_points

            # filled semi-transparent
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], zone.color)
            cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

            # border
            cv2.polylines(frame, [pts], isClosed=True, color=zone.color, thickness=2)

            # label
            cx = int(np.mean([p[0] for p in scaled.points]))
            cy = int(np.mean([p[1] for p in scaled.points]))
            cv2.putText(frame, zone.name, (cx - 30, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    def draw_intrusion_alert(self, frame: np.ndarray, track_id: int,
                             bbox: list, zone_name: str):
        """Flash a red alert box around the intruder."""
        x1, y1, x2, y2 = [int(v) for v in bbox]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
        cv2.putText(frame, f"⚠ {zone_name}", (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)


# ── Serialization helpers ─────────────────────────────────────────────────────

def zones_to_list(zones: list[Zone]) -> list[dict]:
    return [z.to_dict() for z in zones]


def zones_from_list(data: list[dict]) -> list[Zone]:
    return [Zone.from_dict(d) for d in data]
