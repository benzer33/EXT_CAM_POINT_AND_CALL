"""
Zone Page — draw No-Entry polygons on live feed + monitor intrusions.

Left panel : live camera feed with polygon drawing (click to add points)
Right panel: zone list, add/delete/toggle, START/STOP monitoring, event log
"""
from __future__ import annotations

import cv2
import csv
import os
import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QListWidget, QListWidgetItem, QSizePolicy,
    QLineEdit, QCheckBox, QColorDialog, QMessageBox,
    QSplitter, QTextEdit,
)
from PyQt5.QtCore  import Qt, pyqtSlot, pyqtSignal, QPoint, QTimer
from PyQt5.QtGui   import QPixmap, QImage, QColor, QPainter, QPen, QFont

from detection.zone_detector         import Zone, ZoneDetector, zones_to_list, zones_from_list
from services.zone_monitoring_service import ZoneMonitoringService
from database.db_manager             import DBManager
from notification.teams_notifier     import TeamsNotifier
from config.config_manager           import ConfigManager
from camera.camera_manager           import CameraManager


# ── Clickable label for polygon drawing ──────────────────────────────────────

class _DrawLabel(QLabel):
    """QLabel that emits click positions scaled to native resolution."""
    clicked_at = pyqtSignal(int, int)   # x, y in label coords

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked_at.emit(event.x(), event.y())
        super().mousePressEvent(event)


# ── Zone list item ────────────────────────────────────────────────────────────

class _ZoneItem(QListWidgetItem):
    def __init__(self, zone: Zone):
        super().__init__()
        self.zone = zone
        self._refresh()

    def _refresh(self):
        status = "✅" if self.zone.enabled else "⏸"
        pts    = len(self.zone.points)
        self.setText(f"{status}  {self.zone.name}  ({pts} pts)")


# ── Main Zone Page ────────────────────────────────────────────────────────────

class ZonePage(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg      = cfg
        self._service: ZoneMonitoringService | None = None
        self._db       = DBManager(cfg)
        self._notifier = TeamsNotifier(
            webhook_url = cfg.get("teams_webhook", ""),
            send_pass   = False,
            send_fail   = cfg.get("teams_send_fail", True),
        )
        self._db_ok = self._db.init()

        # zones loaded from config
        raw = cfg.get("zone_polygons", [])
        self._zones: list[Zone] = zones_from_list(raw) if raw else []

        # drawing state
        self._drawing       = False
        self._current_pts:  list[tuple[int, int]] = []
        self._draw_color:   QColor = QColor(220, 60, 0)
        self._last_frame:   QImage | None = None
        self._preview_cam:  CameraManager | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._tick_preview)

        self._build_ui()
        self._load_zones_to_list()

    def refresh_config(self):
        """Re-init DB and notifier after settings change."""
        self._db      = DBManager(self._cfg.get("mssql", {}))
        self._db_ok   = self._db.init()
        self._notifier = TeamsNotifier(
            webhook_url = self._cfg.get("teams_webhook", ""),
            send_pass   = False,
            send_fail   = self._cfg.get("teams_send_fail", True),
        )

    def _log_intrusion_csv(self, ev: dict):
        """Write intrusion event to local CSV as fallback when DB is not configured."""
        try:
            csv_path = os.path.join(
                self._cfg.get("capture_dir", "captures"), "zone_events.csv"
            )
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            is_new = not os.path.exists(csv_path)
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["ts", "track_id", "zone_name", "result", "image_path"],
                )
                if is_new:
                    writer.writeheader()
                writer.writerow({
                    "ts":         ev.get("ts", ""),
                    "track_id":   ev.get("track_id", 0),
                    "zone_name":  ev.get("zone_name", ""),
                    "result":     ev.get("result", "INTRUSION"),
                    "image_path": ev.get("image_path", ""),
                })
        except Exception as e:
            print(f"[ZonePage] CSV fallback failed: {e}")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)

        # ── left: feed + drawing tools ────────────────────────────────────────
        left = QWidget()
        lv   = QVBoxLayout(left)
        lv.setContentsMargins(16, 16, 8, 16)
        lv.setSpacing(8)

        title = QLabel("No-Entry Zone Monitor")
        title.setObjectName("PageTitle")
        lv.addWidget(title)

        # drawing toolbar
        draw_bar = QHBoxLayout()
        self._btn_draw   = QPushButton("✏️  Draw Zone")
        self._btn_draw.setCheckable(True)
        self._btn_draw.setFixedHeight(32)
        self._btn_draw.toggled.connect(self._toggle_draw)

        self._btn_undo   = QPushButton("↩ Undo Point")
        self._btn_undo.setFixedHeight(32)
        self._btn_undo.clicked.connect(self._undo_point)

        self._btn_finish = QPushButton("✅  Finish Zone")
        self._btn_finish.setObjectName("StartButton")
        self._btn_finish.setFixedHeight(32)
        self._btn_finish.setEnabled(False)
        self._btn_finish.clicked.connect(self._finish_zone)

        self._btn_color  = QPushButton("🎨  Color")
        self._btn_color.setFixedHeight(32)
        self._btn_color.clicked.connect(self._pick_color)

        self._zone_name_edit = QLineEdit()
        self._zone_name_edit.setPlaceholderText("Zone name…")
        self._zone_name_edit.setFixedWidth(130)
        self._zone_name_edit.setFixedHeight(32)
        self._zone_name_edit.setText("Zone 1")

        for w in (self._btn_draw, self._btn_undo, self._btn_finish,
                  self._btn_color, self._zone_name_edit):
            draw_bar.addWidget(w)
        draw_bar.addStretch()
        lv.addLayout(draw_bar)

        # feed label
        self._feed_lbl = _DrawLabel("Camera not connected")
        self._feed_lbl.setAlignment(Qt.AlignCenter)
        self._feed_lbl.setStyleSheet(
            "color:#3A4A6A; font-size:16px; background:#0D1B2A; border-radius:4px;")
        self._feed_lbl.setMinimumSize(640, 360)
        self._feed_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._feed_lbl.clicked_at.connect(self._on_feed_click)
        lv.addWidget(self._feed_lbl, stretch=1)

        # preview controls
        prev_bar = QHBoxLayout()
        self._btn_preview = QPushButton("📷  Start Preview")
        self._btn_preview.setFixedHeight(30)
        self._btn_preview.clicked.connect(self._toggle_preview)
        prev_bar.addWidget(self._btn_preview)
        prev_bar.addStretch()
        self._hint_lbl = QLabel("Click Draw Zone, then click points on the image")
        self._hint_lbl.setStyleSheet("color:#506080; font-size:11px;")
        prev_bar.addWidget(self._hint_lbl)
        lv.addLayout(prev_bar)

        # ── right: zone list + monitoring ─────────────────────────────────────
        right = QWidget()
        rv    = QVBoxLayout(right)
        rv.setContentsMargins(8, 16, 16, 16)
        rv.setSpacing(10)

        rv.addWidget(QLabel("Zones"))

        self._zone_list = QListWidget()
        self._zone_list.setMaximumHeight(200)
        self._zone_list.itemDoubleClicked.connect(self._toggle_zone_enabled)
        rv.addWidget(self._zone_list)

        zone_btns = QHBoxLayout()
        self._btn_del_zone   = QPushButton("🗑  Delete")
        self._btn_del_zone.setFixedHeight(30)
        self._btn_del_zone.clicked.connect(self._delete_zone)
        self._btn_save_zones = QPushButton("💾  Save Zones")
        self._btn_save_zones.setFixedHeight(30)
        self._btn_save_zones.clicked.connect(self._save_zones)
        for w in (self._btn_del_zone, self._btn_save_zones):
            zone_btns.addWidget(w)
        rv.addLayout(zone_btns)

        # monitoring controls
        mon_frame = QFrame()
        mon_frame.setObjectName("Card")
        mv = QVBoxLayout(mon_frame)
        mv.setContentsMargins(10, 10, 10, 10)
        mv.setSpacing(8)
        mv.addWidget(QLabel("Monitoring"))

        stat_row = QHBoxLayout()
        self._stat_total  = self._make_stat("INTRUSIONS", "0")
        self._stat_inzone = self._make_stat("IN ZONE",    "0")
        self._stat_fps    = self._make_stat("FPS",       "0")
        for w in (self._stat_total, self._stat_inzone, self._stat_fps):
            stat_row.addWidget(w)
        mv.addLayout(stat_row)

        mon_btns = QHBoxLayout()
        self._btn_mon_start = QPushButton("▶  Start")
        self._btn_mon_start.setObjectName("StartButton")
        self._btn_mon_start.setFixedHeight(32)
        self._btn_mon_start.clicked.connect(self._start_monitoring)
        self._btn_mon_stop  = QPushButton("■  Stop")
        self._btn_mon_stop.setObjectName("StopButton")
        self._btn_mon_stop.setFixedHeight(32)
        self._btn_mon_stop.setEnabled(False)
        self._btn_mon_stop.clicked.connect(self._stop_monitoring)
        for w in (self._btn_mon_start, self._btn_mon_stop):
            mon_btns.addWidget(w)
        mv.addLayout(mon_btns)
        rv.addWidget(mon_frame)

        # event log
        rv.addWidget(QLabel("Event Log"))
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setStyleSheet(
            "background:#0A1520; color:#80A0C0; font-size:11px; border-radius:4px;")
        rv.addWidget(self._log_text, stretch=1)

        right.setFixedWidth(320)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        root.addWidget(splitter)

    def _make_stat(self, label: str, value: str) -> QFrame:
        f = QFrame()
        f.setObjectName("Card")
        v = QVBoxLayout(f)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(2)
        val_lbl = QLabel(value)
        val_lbl.setAlignment(Qt.AlignCenter)
        val_lbl.setObjectName("StatValue")
        lbl_lbl = QLabel(label)
        lbl_lbl.setAlignment(Qt.AlignCenter)
        lbl_lbl.setObjectName("StatLabel")
        v.addWidget(val_lbl)
        v.addWidget(lbl_lbl)
        f._val = val_lbl   # type: ignore[attr-defined]
        return f

    # ── preview ───────────────────────────────────────────────────────────────

    def _toggle_preview(self):
        if self._preview_timer.isActive():
            self._preview_timer.stop()
            if self._preview_cam:
                self._preview_cam.disconnect()
                self._preview_cam = None
            self._btn_preview.setText("📷  Start Preview")
        else:
            self._preview_cam = CameraManager()
            src = self._cfg.get("camera_source", 0)
            if not self._preview_cam.connect(src):
                QMessageBox.warning(self, "Camera Error",
                                    f"Cannot open camera: {src}")
                self._preview_cam = None
                return
            self._preview_timer.start(66)   # ~15 fps
            self._btn_preview.setText("⏹  Stop Preview")

    def _tick_preview(self):
        if self._service and self._service.isRunning():
            return   # live feed comes from service signal
        if self._preview_cam:
            frame = self._preview_cam.read()
            if frame is not None:
                if self._cfg.get("mirror_feed", False):
                    frame = cv2.flip(frame, 1)
                self._last_frame = _to_qimage(frame)
                self._refresh_feed()

    # ── polygon drawing ───────────────────────────────────────────────────────

    def _toggle_draw(self, checked: bool):
        self._drawing = checked
        self._current_pts.clear()
        self._btn_finish.setEnabled(False)
        hint = "Click on image to add polygon points" if checked else \
               "Click Draw Zone, then click points on the image"
        self._hint_lbl.setText(hint)
        self._btn_draw.setText("🚫  Cancel Draw" if checked else "✏️  Draw Zone")

    def _on_feed_click(self, lx: int, ly: int):
        if not self._drawing:
            return
        # map label coords to native image coords
        lw = self._feed_lbl.width()
        lh = self._feed_lbl.height()
        if self._last_frame:
            iw = self._last_frame.width()
            ih = self._last_frame.height()
            # account for aspect-ratio letterbox scaling
            scale = min(lw / iw, lh / ih)
            ox    = (lw - iw * scale) / 2
            oy    = (lh - ih * scale) / 2
            nx = int((lx - ox) / scale)
            ny = int((ly - oy) / scale)
        else:
            nx, ny = lx, ly

        self._current_pts.append((nx, ny))
        self._btn_finish.setEnabled(len(self._current_pts) >= 3)
        self._refresh_feed()

    def _undo_point(self):
        if self._current_pts:
            self._current_pts.pop()
        self._btn_finish.setEnabled(len(self._current_pts) >= 3)
        self._refresh_feed()

    def _finish_zone(self):
        if len(self._current_pts) < 3:
            return
        name  = self._zone_name_edit.text().strip() or f"Zone {len(self._zones)+1}"
        color = (self._draw_color.blue(),
                 self._draw_color.green(),
                 self._draw_color.red())   # QColor RGB → BGR
        zone  = Zone(name=name, points=list(self._current_pts), color=color)
        self._zones.append(zone)
        self._current_pts.clear()
        self._drawing = False
        self._btn_draw.setChecked(False)
        self._btn_finish.setEnabled(False)
        self._hint_lbl.setText("Zone added — save when ready")
        self._zone_name_edit.setText(f"Zone {len(self._zones)+1}")
        self._load_zones_to_list()
        self._refresh_feed()

    def _pick_color(self):
        col = QColorDialog.getColor(self._draw_color, self, "Pick Zone Color")
        if col.isValid():
            self._draw_color = col

    def _refresh_feed(self):
        if self._last_frame is None:
            return
        # composite: draw zones + current polygon
        img = self._last_frame.copy()
        # convert to cv2
        buf   = img.bits(); buf.setsize(img.byteCount())
        arr   = np.frombuffer(buf, dtype=np.uint8).reshape((img.height(), img.width(), 3))
        frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        fw, fh = frame.shape[1], frame.shape[0]

        # draw saved zones
        saved_w = self._cfg.get("zone_saved_w", fw)
        saved_h = self._cfg.get("zone_saved_h", fh)
        tmp_det = ZoneDetector(self._zones, saved_w, saved_h)
        tmp_det.draw_zones(frame, fw, fh)

        # draw in-progress polygon
        if self._current_pts:
            col = (self._draw_color.blue(),
                   self._draw_color.green(),
                   self._draw_color.red())
            for p in self._current_pts:
                cv2.circle(frame, p, 5, col, -1)
            if len(self._current_pts) >= 2:
                cv2.polylines(frame,
                              [np.array(self._current_pts, dtype=np.int32)],
                              False, col, 2)

        pix = QPixmap.fromImage(_to_qimage(frame)).scaled(
            self._feed_lbl.width(), self._feed_lbl.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._feed_lbl.setPixmap(pix)

    # ── zone list management ──────────────────────────────────────────────────

    def _load_zones_to_list(self):
        self._zone_list.clear()
        for z in self._zones:
            self._zone_list.addItem(_ZoneItem(z))

    def _toggle_zone_enabled(self, item: _ZoneItem):
        item.zone.enabled = not item.zone.enabled
        item._refresh()

    def _delete_zone(self):
        row = self._zone_list.currentRow()
        if 0 <= row < len(self._zones):
            self._zones.pop(row)
            self._load_zones_to_list()
            self._refresh_feed()

    def _save_zones(self):
        # save canvas resolution so we can rescale later
        if self._last_frame:
            self._cfg["zone_saved_w"] = self._last_frame.width()
            self._cfg["zone_saved_h"] = self._last_frame.height()
        self._cfg["zone_polygons"] = zones_to_list(self._zones)
        ConfigManager().save(self._cfg)
        QMessageBox.information(self, "Saved",
                                f"{len(self._zones)} zone(s) saved to config.")

    # ── monitoring ────────────────────────────────────────────────────────────

    def _start_monitoring(self):
        if self._service and self._service.isRunning():
            return
        if not self._zones:
            QMessageBox.warning(
                self, "No Zones",
                "No zones defined. Draw and save at least one zone first."
            )
            return
        if self._preview_timer.isActive():
            self._preview_timer.stop()
            if self._preview_cam:
                self._preview_cam.disconnect()
                self._preview_cam = None

        # Always push the current in-memory zones into service directly —
        # do NOT rely on config polygons being up-to-date.
        self._service = ZoneMonitoringService(self._cfg)
        self._service.set_zones(list(self._zones))
        self._service.frame_ready.connect(self._on_frame)
        self._service.stats_updated.connect(self._on_stats)
        self._service.intrusion_event.connect(self._on_intrusion)
        self._service.status_changed.connect(self.status_message)
        self._service.error_occurred.connect(self._on_error)
        self._service.start()
        self._btn_mon_start.setEnabled(False)
        self._btn_mon_stop.setEnabled(True)

    def _stop_monitoring(self):
        if self._service:
            self._service.stop()
            self._service.wait(3000)
            self._service = None
        self._btn_mon_start.setEnabled(True)
        self._btn_mon_stop.setEnabled(False)

    # ── slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(QImage)
    def _on_frame(self, img: QImage):
        self._last_frame = img
        pix = QPixmap.fromImage(img).scaled(
            self._feed_lbl.width(), self._feed_lbl.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._feed_lbl.setPixmap(pix)

    @pyqtSlot(dict)
    def _on_stats(self, s: dict):
        self._stat_total._val.setText(str(s.get("total", 0)))
        self._stat_inzone._val.setText(str(s.get("in_zone", 0)))
        self._stat_fps._val.setText(str(s.get("fps", 0)))

    @pyqtSlot(dict)
    def _on_intrusion(self, ev: dict):
        ts    = ev.get("ts", "")
        zname = ev.get("zone_name", "?")
        tid   = ev.get("track_id", 0)
        img   = ev.get("image_path", "")
        self._log_text.append(
            f"[{ts}] ⚠️  Track #{tid} entered  <b>{zname}</b>"
            + (f"  <span style='color:#507090'>📷 {os.path.basename(img)}</span>" if img else "")
        )
        if self._db_ok:
            self._db.log_crossing(
                track_id   = tid,
                result     = "INTRUSION",
                mode       = f"ZONE:{zname}",
                image_path = img,
            )
        else:
            self._log_intrusion_csv(ev)
            self._log_text.append(
                "<span style='color:#806040'>  ⚠ DB not configured — saved to zone_events.csv</span>"
            )
        self._notifier.notify(
            track_id   = tid,
            result     = "INTRUSION",
            mode       = f"ZONE:{zname}",
            image_path = img,
        )
        self.status_message.emit(f"⚠️ Intrusion: Track #{tid} in {zname}  {ts}")

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self.status_message.emit(f"ZONE ERROR: {msg}")
        self._stop_monitoring()

    def closeEvent(self, event):
        self._stop_monitoring()
        super().closeEvent(event)


# ── helper ────────────────────────────────────────────────────────────────────

def _to_qimage(frame: np.ndarray) -> QImage:
    import cv2
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
