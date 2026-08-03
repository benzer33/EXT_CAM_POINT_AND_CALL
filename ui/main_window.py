"""Main window — sidebar + stacked pages."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QStatusBar,
)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui  import QFont

from ui.pages.dashboard_page     import DashboardPage
from ui.pages.camera_page        import CameraPage
from ui.pages.calibration_page   import CalibrationPage
from ui.pages.detection_page     import DetectionPage
from ui.pages.history_page       import HistoryPage
from ui.pages.notification_page  import NotificationPage
from ui.pages.settings_page      import SettingsPage
from ui.pages.rtsp_scanner_page  import RTSPScannerPage
from ui.pages.zone_page          import ZonePage

# nav groups: (section_label, [(page_key, button_label), ...])
_NAV_GROUPS = [
    ("MONITORING", [
        ("dashboard",    "⬛  Dashboard"),
        ("zone_monitor", "🚫  No-Entry Zone"),
    ]),
    ("SETUP", [
        ("rtsp_scanner", "🔎  RTSP Scanner"),
        ("camera",       "📷  Camera"),
        ("detection",    "🔍  Detection"),
        ("calibration",  "📐  Calibration"),
    ]),
    ("REPORTS & CONFIG", [
        ("history",      "📋  History"),
        ("notification", "🔔  Notification"),
        ("settings",     "⚙️  Settings"),
    ]),
]
# flat ordered list for backward compat
_NAV = [(k, lbl) for _, items in _NAV_GROUPS for k, lbl in items]


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg          = cfg
        self._page_map:    dict[str, QWidget]      = {}
        self._nav_buttons: dict[str, QPushButton]  = {}
        self._active_page  = ""
        self.setWindowTitle("Point & Call Monitoring System")
        self.setMinimumSize(1280, 720)
        self._build_ui()
        self._navigate("dashboard")

    def _build_ui(self):
        root = QWidget(); hbox = QHBoxLayout(root); hbox.setContentsMargins(0,0,0,0); hbox.setSpacing(0)
        hbox.addWidget(self._build_sidebar())
        hbox.addWidget(self._build_content(), stretch=1)
        self.setCentralWidget(root)
        self._status_bar = QStatusBar(); self._status_bar.showMessage("Ready"); self.setStatusBar(self._status_bar)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget(); sidebar.setObjectName("Sidebar")
        vbox = QVBoxLayout(sidebar); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)
        t = QLabel("POINT & CALL"); t.setObjectName("SidebarTitle")
        s = QLabel("Monitoring System"); s.setObjectName("SidebarSubtitle")
        vbox.addWidget(t); vbox.addWidget(s)
        div = QWidget(); div.setFixedHeight(1); div.setStyleSheet("background:#1A3A6A;")
        vbox.addWidget(div); vbox.addSpacing(4)

        for group_label, items in _NAV_GROUPS:
            # section header
            hdr = QLabel(group_label)
            hdr.setStyleSheet(
                "color:#2A5A8A; font-size:9px; font-weight:bold; "
                "padding:6px 12px 2px 12px; letter-spacing:1px;"
            )
            vbox.addWidget(hdr)
            for key, label in items:
                btn = QPushButton(label); btn.setObjectName("NavButton")
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda _, k=key: self._navigate(k))
                self._nav_buttons[key] = btn; vbox.addWidget(btn)
            # thin separator between groups
            sep = QWidget(); sep.setFixedHeight(1)
            sep.setStyleSheet("background:#0D1E30; margin:4px 0;")
            vbox.addWidget(sep)

        vbox.addStretch()
        ver = QLabel("v1.0.0"); ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet("color:#2A3A5A; font-size:10px; padding:8px;")
        vbox.addWidget(ver)
        return sidebar

    def _build_content(self) -> QWidget:
        self._stack = QStackedWidget(); self._stack.setObjectName("ContentStack")
        db_page      = DashboardPage(self._cfg, self)
        cam_page     = CameraPage(self._cfg, self)
        cal_page     = CalibrationPage(self._cfg, self)
        det_page     = DetectionPage(self._cfg, self)
        hist_page    = HistoryPage(self._cfg, self)
        notif_page   = NotificationPage(self._cfg, self)
        sett_page    = SettingsPage(self._cfg, self)
        scanner_page = RTSPScannerPage(self._cfg, self)
        zone_page    = ZonePage(self._cfg, self)
        for key, page in [
                ("dashboard",    db_page),
                ("camera",       cam_page),
                ("calibration",  cal_page),
                ("detection",    det_page),
                ("history",      hist_page),
                ("notification", notif_page),
                ("settings",     sett_page),
                ("rtsp_scanner", scanner_page),
                ("zone_monitor", zone_page),
        ]:
            self._stack.addWidget(page)
            self._page_map[key] = page
        db_page.status_message.connect(self._on_status)
        cam_page.camera_connected.connect(db_page.on_camera_source_changed)
        sett_page.config_saved.connect(db_page.refresh_config)
        sett_page.config_saved.connect(zone_page.refresh_config)
        # when a camera is picked in scanner, update shared config + camera page
        scanner_page.camera_selected.connect(self._on_scanner_camera_selected)
        zone_page.status_message.connect(self._on_status)
        return self._stack

    def _navigate(self, key: str):
        if key not in self._page_map: return
        if self._active_page and self._active_page in self._nav_buttons:
            btn = self._nav_buttons[self._active_page]
            btn.setProperty("active", "false"); btn.setStyle(btn.style())
        self._active_page = key
        btn = self._nav_buttons[key]
        btn.setProperty("active", "true"); btn.setStyle(btn.style())
        self._stack.setCurrentWidget(self._page_map[key])
        if key == "history":
            self._page_map["history"].refresh()

    @pyqtSlot(str, str)
    def _on_scanner_camera_selected(self, ip: str, url: str):
        """Apply scanner selection to shared config and notify camera page."""
        self._cfg["camera_source"] = url
        cam_page = self._page_map.get("camera")
        if cam_page and hasattr(cam_page, "set_source"):
            cam_page.set_source(url)
        db_page = self._page_map.get("dashboard")
        if db_page and hasattr(db_page, "on_camera_source_changed"):
            db_page.on_camera_source_changed(url)
        self._on_status(f"📷  Camera set: {ip}  →  {url.split('@')[-1]}")
        self._navigate("dashboard")

    @pyqtSlot(str)
    def _on_status(self, msg: str):
        self._status_bar.showMessage(msg)

    def closeEvent(self, event):
        dash = self._page_map.get("dashboard")
        if dash: dash.stop_monitoring()
        zone = self._page_map.get("zone_monitor")
        if zone: zone._stop_monitoring()
        event.accept()
