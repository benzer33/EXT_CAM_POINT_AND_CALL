"""Dashboard page — live feed + stats + START/STOP."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy,
)
from PyQt5.QtCore  import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui   import QPixmap, QImage

from services.monitoring_service import MonitoringService
from database.db_manager         import DBManager
from notification.teams_notifier import TeamsNotifier
from config.config_manager       import ConfigManager


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
        self._feed_lbl = QLabel("Camera not connected")
        self._feed_lbl.setAlignment(Qt.AlignCenter)
        self._feed_lbl.setStyleSheet(
            "color:#3A4A6A; font-size:16px; background:#0D1B2A; border-radius:4px;"
        )
        self._feed_lbl.setMinimumSize(640, 360)
        self._feed_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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

        for btn in (self._btn_start, self._btn_stop, self._btn_reset):
            btn.setFixedWidth(140)
            vbox.addWidget(btn)

        return panel

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
