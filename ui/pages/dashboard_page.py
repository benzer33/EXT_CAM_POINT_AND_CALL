"""Dashboard page — live feed + stats + START/STOP + Detection Zone drawing."""
from __future__ import annotations

import cv2
import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QMessageBox,
)
from PyQt5.QtCore  import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt5.QtGui   import QPixmap, QImage, QPainter, QPen, QColor, QPolygon

from services.monitoring_service import MonitoringService
from database.db_manager         import DBManager
from notification.teams_notifier import TeamsNotifier
from config.config_manager       import ConfigManager



# ── Clickable feed label for zone drawing ────────────────────────────────────

class _DrawLabel(QLabel):
    """QLabel that emits mouse-click positions and draws the in-progress polygon."""
    clicked_at = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[tuple[int, int]] = []
        self._drawing = False

    def set_drawing(self, enabled: bool):
        self._drawing = enabled
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)

    def set_points(self, pts: list[tuple[int, int]]):
        self._points = list(pts)
        self.update()

    def clear_points(self):
        self._points = []
        self.update()

    def mousePressEvent(self, event):
        if self._drawing and event.button() == Qt.LeftButton:
            self.clicked_at.emit(event.x(), event.y())
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if len(self._points) < 2:
            return
        painter = QPainter(self)
        pen = QPen(QColor(0, 220, 80), 2, Qt.SolidLine)
        painter.setPen(pen)
        pts = [QPoint(x, y) for x, y in self._points]
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])
        # close polygon visually
        if len(pts) >= 3:
            painter.drawLine(pts[-1], pts[0])
        # draw vertex dots
        painter.setBrush(QColor(0, 220, 80))
        for p in pts:
            painter.drawEllipse(p, 4, 4)
        painter.end()


# ── Stat box ─────────────────────────────────────────────────────────────────

class _StatBox(QFrame):
    def __init__(self, label: str, value_obj: str = "StatValue", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(12, 10, 12, 10)
        vbox.setSpacing(2)
        self._value = QLabel("0")
        self._value.setObjectName(value_obj)
        self._value.setAlignment(Qt.AlignCenter)
        self._label = QLabel(label)
        self._label.setObjectName("StatLabel")
        self._label.setAlignment(Qt.AlignCenter)
        vbox.addWidget(self._value)
        vbox.addWidget(self._label)
        self.setFixedWidth(130)

    def set_value(self, v):
        self._value.setText(str(v))


class DashboardPage(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg      = cfg
        self._service: MonitoringService | None = None
        self._db       = DBManager(cfg.get("mssql", {}))
        self._notifier = TeamsNotifier(
            webhook_url = cfg.get("teams_webhook", ""),
            send_pass   = cfg.get("teams_send_pass", False),
            send_fail   = cfg.get("teams_send_fail", True),
        )
        self._db.init()

        # zone drawing state
        self._drawing_zone  = False
        self._zone_pts:     list[tuple[int, int]] = []  # points in label coords
        self._zone_saved:   list[tuple[int, int]] = []  # committed zone in label coords
        self._zone_lbl_w:   int = 1
        self._zone_lbl_h:   int = 1

        # restore saved zone from config
        raw = cfg.get("dashboard_zone", [])
        if raw:
            self._zone_saved = [tuple(p) for p in raw]

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title_row = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self._mode_lbl = QLabel("Mode: STRICT")
        self._mode_lbl.setStyleSheet("color:#00A0CC; font-weight:bold; font-size:13px;")
        title_row.addWidget(self._mode_lbl)
        root.addLayout(title_row)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_feed_panel(), stretch=3)
        body.addWidget(self._build_right_panel(), stretch=0)
        root.addLayout(body, stretch=1)

    def _build_feed_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        # zone drawing toolbar
        toolbar = QHBoxLayout()
        self._btn_draw_zone = QPushButton("✏️  Draw Zone")
        self._btn_draw_zone.setCheckable(True)
        self._btn_draw_zone.setFixedHeight(26)
        self._btn_draw_zone.setStyleSheet(
            "font-size:12px; padding:0 8px;"
            "background:#1A3A2A; color:#00C853; border:1px solid #00C853; border-radius:3px;"
        )
        self._btn_draw_zone.clicked.connect(self._toggle_draw_zone)

        self._btn_finish_zone = QPushButton("✔  Finish Zone")
        self._btn_finish_zone.setFixedHeight(26)
        self._btn_finish_zone.setEnabled(False)
        self._btn_finish_zone.setStyleSheet(
            "font-size:12px; padding:0 8px;"
            "background:#1A3A2A; color:#00FF88; border:1px solid #00C853; border-radius:3px;"
        )
        self._btn_finish_zone.clicked.connect(self._finish_zone)

        self._btn_clear_zone = QPushButton("🗑  Clear Zone")
        self._btn_clear_zone.setFixedHeight(26)
        self._btn_clear_zone.setStyleSheet(
            "font-size:12px; padding:0 8px;"
            "background:#2A1A1A; color:#FF6060; border:1px solid #CC3333; border-radius:3px;"
        )
        self._btn_clear_zone.clicked.connect(self._clear_zone)

        self._zone_lbl_status = QLabel("")
        self._zone_lbl_status.setStyleSheet("color:#506080; font-size:11px;")

        for w in (self._btn_draw_zone, self._btn_finish_zone,
                  self._btn_clear_zone, self._zone_lbl_status):
            toolbar.addWidget(w)
        toolbar.addStretch()
        vbox.addLayout(toolbar)

        self._feed_lbl = _DrawLabel()
        self._feed_lbl.setAlignment(Qt.AlignCenter)
        self._feed_lbl.setStyleSheet(
            "color:#3A4A6A; font-size:16px; background:#0D1B2A; border-radius:4px;"
        )
        self._feed_lbl.setText("Camera not connected")
        self._feed_lbl.setMinimumSize(640, 360)
        self._feed_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._feed_lbl.clicked_at.connect(self._on_feed_click)
        vbox.addWidget(self._feed_lbl)
        return frame

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(150)
        vbox  = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)

        self._stat_total  = _StatBox("TOTAL",   "StatValue")
        self._stat_pass   = _StatBox("PASS",    "StatValuePass")
        self._stat_fail   = _StatBox("FAIL",    "StatValueFail")
        self._stat_inzone = _StatBox("IN ZONE", "StatValue")
        self._stat_fps    = _StatBox("FPS",     "StatValue")

        for sb in (self._stat_total, self._stat_pass,
                   self._stat_fail, self._stat_inzone, self._stat_fps):
            vbox.addWidget(sb)

        vbox.addStretch()

        self._btn_start = QPushButton("▶  START")
        self._btn_start.setObjectName("StartButton")
        self._btn_start.clicked.connect(self.start_monitoring)

        self._btn_stop = QPushButton("■  STOP")
        self._btn_stop.setObjectName("StopButton")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self.stop_monitoring)

        self._btn_reset = QPushButton("↺  Reset")
        self._btn_reset.clicked.connect(self._reset_counters)

        self._btn_save_zone = QPushButton("💾  Save Zone")
        self._btn_save_zone.setFixedWidth(140)
        self._btn_save_zone.setStyleSheet(
            "background:#1A2E1A; color:#00C853; border:1px solid #00C853; border-radius:4px;"
        )
        self._btn_save_zone.clicked.connect(self._save_zone_to_config)

        for btn in (self._btn_start, self._btn_stop, self._btn_reset, self._btn_save_zone):
            btn.setFixedWidth(140)
            vbox.addWidget(btn)

        return panel

    # ── zone drawing ─────────────────────────────────────────────────────────
    def _toggle_draw_zone(self, checked: bool):
        self._drawing_zone = checked
        self._feed_lbl.set_drawing(checked)
        if checked:
            self._zone_pts = []
            self._feed_lbl.set_points([])
            self._btn_finish_zone.setEnabled(False)
            self._zone_lbl_status.setText("คลิกบนภาพเพื่อวางจุด…")
        else:
            self._zone_lbl_status.setText("")

    def _on_feed_click(self, x: int, y: int):
        if not self._drawing_zone:
            return
        self._zone_pts.append((x, y))
        self._feed_lbl.set_points(self._zone_pts)
        self._zone_lbl_status.setText(f"{len(self._zone_pts)} จุด — กด Finish Zone เมื่อครบ")
        if len(self._zone_pts) >= 3:
            self._btn_finish_zone.setEnabled(True)

    def _finish_zone(self):
        if len(self._zone_pts) < 3:
            return
        self._zone_saved   = list(self._zone_pts)
        self._zone_lbl_w   = self._feed_lbl.width()
        self._zone_lbl_h   = self._feed_lbl.height()
        self._zone_pts     = []
        self._drawing_zone = False
        self._btn_draw_zone.setChecked(False)
        self._feed_lbl.set_drawing(False)
        self._feed_lbl.set_points(self._zone_saved)
        self._btn_finish_zone.setEnabled(False)
        self._zone_lbl_status.setText(
            f"✅  โซนวาดแล้ว ({len(self._zone_saved)} จุด) — กด Save Zone เพื่อบันทึก"
        )
        # push to running service immediately
        self._push_zone_to_service()

    def _clear_zone(self):
        self._zone_saved   = []
        self._zone_pts     = []
        self._drawing_zone = False
        self._btn_draw_zone.setChecked(False)
        self._feed_lbl.set_drawing(False)
        self._feed_lbl.clear_points()
        self._zone_lbl_status.setText("โซนถูกลบออกแล้ว")
        if self._service:
            self._service.clear_zone()

    def _push_zone_to_service(self):
        if self._service and self._zone_saved:
            self._service.set_zone(
                self._zone_saved,
                saved_w = self._zone_lbl_w,
                saved_h = self._zone_lbl_h,
            )

    def _save_zone_to_config(self):
        if not self._zone_saved:
            QMessageBox.information(self, "ยังไม่มีโซน", "กรุณาวาดโซนก่อน")
            return
        self._cfg["dashboard_zone"]   = [list(p) for p in self._zone_saved]
        self._cfg["dashboard_zone_w"] = self._zone_lbl_w
        self._cfg["dashboard_zone_h"] = self._zone_lbl_h
        ConfigManager().save(self._cfg)
        self._zone_lbl_status.setText("✅  บันทึกโซนเรียบร้อย")

    # ── monitoring ────────────────────────────────────────────────────────────
    def refresh_config(self, cfg: dict):
        """Call this after Settings are saved so DB + notifier use the latest config."""
        self._cfg = cfg
        self._db  = DBManager(cfg.get("mssql", {}))
        self._db.init()
        self._notifier = TeamsNotifier(
            webhook_url = cfg.get("teams_webhook", ""),
            send_pass   = cfg.get("teams_send_pass", False),
            send_fail   = cfg.get("teams_send_fail", True),
        )

    def start_monitoring(self):
        if self._service and self._service.isRunning():
            return
        self._service = MonitoringService(self._cfg)
        self._service.frame_ready.connect(self._on_frame)
        self._service.stats_updated.connect(self._on_stats)
        self._service.crossing_event.connect(self._on_crossing)
        self._service.status_changed.connect(self.status_message)
        self._service.error_occurred.connect(self._on_error)
        self._service.start()
        # restore zone into service
        if self._zone_saved:
            self._push_zone_to_service()
        elif self._cfg.get("dashboard_zone"):
            pts = [tuple(p) for p in self._cfg["dashboard_zone"]]
            w   = self._cfg.get("dashboard_zone_w", self._feed_lbl.width() or 1280)
            h   = self._cfg.get("dashboard_zone_h", self._feed_lbl.height() or 720)
            self._zone_saved  = pts
            self._zone_lbl_w  = w
            self._zone_lbl_h  = h
            self._feed_lbl.set_points(pts)
            self._service.set_zone(pts, w, h)
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._update_mode_label()

    def stop_monitoring(self):
        if self._service:
            self._service.stop()
            self._service.wait(3000)
            self._service = None
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._feed_lbl.setText("Camera not connected")
        self._feed_lbl.setPixmap(QPixmap())

    def _reset_counters(self):
        if self._service:
            self._service.reset_counters()

    # ── slots ─────────────────────────────────────────────────────────────────
    @pyqtSlot(QImage)
    def _on_frame(self, img: QImage):
        pix = QPixmap.fromImage(img).scaled(
            self._feed_lbl.width(), self._feed_lbl.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._feed_lbl.setPixmap(pix)

    @pyqtSlot(dict)
    def _on_stats(self, s: dict):
        self._stat_total.set_value(s.get("total",   0))
        self._stat_pass.set_value( s.get("pass",    0))
        self._stat_fail.set_value( s.get("fail",    0))
        self._stat_inzone.set_value(s.get("in_zone",0))
        self._stat_fps.set_value(  s.get("fps",   0.0))

    @pyqtSlot(dict)
    def _on_crossing(self, event: dict):
        track_id   = event["track_id"]
        result     = event["result"]
        mode       = event["mode"]
        image_path = event.get("image_path", "")
        ts         = event.get("ts", "")

        self._db.log_crossing(
            track_id   = track_id,
            result     = result,
            mode       = mode,
            image_path = image_path,
        )
        self._notifier.notify(
            track_id   = track_id,
            result     = result,
            mode       = mode,
            image_path = image_path,
        )
        icon = "✅" if result == "PASS" else "⚠️"
        self.status_message.emit(
            f"{icon} Track #{track_id}  {result}  [{mode}]  {ts}"
        )

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self.status_message.emit(f"ERROR: {msg}")
        self.stop_monitoring()

    @pyqtSlot(object)
    def on_camera_source_changed(self, source):
        self._cfg["camera_source"] = source
        self.status_message.emit(f"Camera source updated: {source}")

    def _update_mode_label(self):
        mode  = self._cfg.get("sensitivity", "STRICT")
        color = "#00C853" if mode == "LOOSE" else "#00A0CC"
        self._mode_lbl.setText(f"Mode: {mode}")
        self._mode_lbl.setStyleSheet(f"color:{color}; font-weight:bold; font-size:13px;")
