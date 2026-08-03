"""
RTSP Scanner Page — scan LAN, show 3×3 camera grid, select & save.
"""
from __future__ import annotations

from urllib.parse import urlparse, unquote

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QGridLayout, QScrollArea, QLineEdit,
    QGroupBox, QFormLayout, QSizePolicy, QMessageBox, QDialog,
    QDialogButtonBox,
)
from PyQt5.QtCore  import Qt, pyqtSlot, pyqtSignal, QSize
from PyQt5.QtGui   import QPixmap, QImage, QFont, QCursor

from camera.rtsp_scanner   import RTSPScanner
from camera.rtsp_profiles  import RTSPProfile, RTSPProfileManager
from config.config_manager import ConfigManager


# ── Single camera card ────────────────────────────────────────────────────────

class _CameraCard(QFrame):
    """Thumbnail card shown in the grid; click to select."""

    selected = pyqtSignal(str, str)   # ip, url

    THUMB_W, THUMB_H = 256, 144

    def __init__(self, ip: str, url: str, preview: QImage, parent=None):
        super().__init__(parent)
        self.ip  = ip
        self.url = url
        self._selected = False

        self.setObjectName("CameraCard")
        self.setFixedSize(self.THUMB_W + 16, self.THUMB_H + 52)
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        self._img_lbl = QLabel()
        self._img_lbl.setFixedSize(self.THUMB_W, self.THUMB_H)
        self._img_lbl.setAlignment(Qt.AlignCenter)
        self._img_lbl.setStyleSheet("background:#0D1B2A; border-radius:3px;")
        vbox.addWidget(self._img_lbl)

        self._ip_lbl = QLabel(ip)
        self._ip_lbl.setAlignment(Qt.AlignCenter)
        self._ip_lbl.setStyleSheet("color:#A0B4CC; font-size:11px; font-weight:bold;")
        vbox.addWidget(self._ip_lbl)

        url_short = url.split("@")[-1] if "@" in url else url
        self._url_lbl = QLabel(url_short[:38] + "…" if len(url_short) > 38 else url_short)
        self._url_lbl.setAlignment(Qt.AlignCenter)
        self._url_lbl.setStyleSheet("color:#506080; font-size:9px;")
        self._url_lbl.setWordWrap(True)
        vbox.addWidget(self._url_lbl)

        self.set_preview(preview)
        self._refresh_style()

    def set_preview(self, img: QImage):
        pix = QPixmap.fromImage(img).scaled(
            self.THUMB_W, self.THUMB_H,
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._img_lbl.setPixmap(pix)

    def set_selected(self, v: bool):
        self._selected = v
        self._refresh_style()

    def _refresh_style(self):
        border = "#00C8FF" if self._selected else "#1A2A3A"
        bg     = "#0D2030"  if self._selected else "#111820"
        self.setStyleSheet(
            f"QFrame#CameraCard {{ border: 2px solid {border}; "
            f"border-radius:6px; background:{bg}; }}"
        )

    def mousePressEvent(self, event):
        self.selected.emit(self.ip, self.url)
        super().mousePressEvent(event)


# ── Credential dialog ─────────────────────────────────────────────────────────

class _CredentialDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scan Credentials")
        self.setFixedWidth(340)
        form = QFormLayout(self)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        self._u1 = QLineEdit("admin");         self._u1.setPlaceholderText("username 1")
        self._p1 = QLineEdit("REDACTED_CAMERA_PASSWORD");     self._p1.setPlaceholderText("password 1")
        self._p1.setEchoMode(QLineEdit.Password)
        self._u2 = QLineEdit("admin");         self._u2.setPlaceholderText("username 2")
        self._p2 = QLineEdit("REDACTED_CAMERA_PASSWORD");     self._p2.setPlaceholderText("password 2")
        self._p2.setEchoMode(QLineEdit.Password)

        form.addRow("User 1:",     self._u1)
        form.addRow("Password 1:", self._p1)
        form.addRow("User 2:",     self._u2)
        form.addRow("Password 2:", self._p2)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def credentials(self) -> list[tuple[str, str]]:
        pairs = []
        for u, p in [(self._u1, self._p1), (self._u2, self._p2)]:
            if u.text().strip():
                pairs.append((u.text().strip(), p.text()))
        return pairs or [("admin", "admin")]


# ── Main scanner page ─────────────────────────────────────────────────────────

class RTSPScannerPage(QWidget):
    """Full LAN RTSP scanner with 3×3 (expandable) grid preview."""

    camera_selected = pyqtSignal(str, str)   # ip, url — consumed by CameraPage

    COLS = 3

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg      = cfg
        self._scanner: RTSPScanner | None = None
        self._cards:   list[_CameraCard]  = []
        self._selected_url = ""
        self._selected_ip  = ""
        self._credentials: list[tuple[str, str]] = [
            ("admin", "REDACTED_CAMERA_PASSWORD"),
            ("admin", "REDACTED_CAMERA_PASSWORD"),
        ]
        self._build_ui()

    # ── UI build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # title row
        title_row = QHBoxLayout()
        title = QLabel("RTSP Camera Scanner")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        root.addLayout(title_row)

        # toolbar
        bar = QHBoxLayout()
        self._btn_scan = QPushButton("🔍  Scan Network")
        self._btn_scan.setObjectName("StartButton")
        self._btn_scan.setFixedHeight(34)
        self._btn_scan.clicked.connect(self._start_scan)

        self._btn_creds = QPushButton("🔑  Credentials")
        self._btn_creds.setFixedHeight(34)
        self._btn_creds.clicked.connect(self._edit_credentials)

        self._btn_stop = QPushButton("⏹  Stop")
        self._btn_stop.setFixedHeight(34)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_scan)

        self._btn_use = QPushButton("✅  Use Selected Camera")
        self._btn_use.setObjectName("StartButton")
        self._btn_use.setFixedHeight(34)
        self._btn_use.setEnabled(False)
        self._btn_use.clicked.connect(self._use_selected)

        self._btn_save = QPushButton("💾  Save to Config")
        self._btn_save.setFixedHeight(34)
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._save_selected)

        for w in (self._btn_scan, self._btn_creds, self._btn_stop):
            bar.addWidget(w)
        bar.addStretch()
        for w in (self._btn_use, self._btn_save):
            bar.addWidget(w)
        root.addLayout(bar)

        # manual IP row
        ip_row = QHBoxLayout()
        ip_lbl = QLabel("Scan specific IP:")
        ip_lbl.setStyleSheet("color:#80A0C0; font-size:12px;")
        ip_lbl.setFixedWidth(120)
        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("e.g.  192.168.254.190  or  192.168.254.1-254")
        self._ip_edit.setFixedHeight(30)
        self._ip_edit.returnPressed.connect(self._scan_ip_manual)
        self._btn_scan_ip = QPushButton("🔎  Scan IP")
        self._btn_scan_ip.setFixedHeight(30)
        self._btn_scan_ip.setFixedWidth(90)
        self._btn_scan_ip.clicked.connect(self._scan_ip_manual)
        ip_row.addWidget(ip_lbl)
        ip_row.addWidget(self._ip_edit, stretch=1)
        ip_row.addWidget(self._btn_scan_ip)
        root.addLayout(ip_row)

        # progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(14)
        self._progress.setTextVisible(True)
        self._progress.setFormat("Ready — press Scan Network to begin")
        root.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#506080; font-size:11px;")
        root.addWidget(self._status_lbl)

        # selected camera detail bar
        self._detail_frame = QFrame()
        self._detail_frame.setObjectName("Card")
        detail_layout = QHBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(12, 6, 12, 6)
        self._detail_lbl = QLabel("No camera selected")
        self._detail_lbl.setStyleSheet("color:#80A0C0; font-size:12px;")
        detail_layout.addWidget(self._detail_lbl)
        root.addWidget(self._detail_frame)

        # grid scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._grid_widget)
        root.addWidget(scroll, stretch=1)

    # ── scan control ──────────────────────────────────────────────────────────

    def _edit_credentials(self):
        dlg = _CredentialDialog(self)
        # pre-fill
        if self._credentials:
            dlg._u1.setText(self._credentials[0][0])
            dlg._p1.setText(self._credentials[0][1])
        if len(self._credentials) > 1:
            dlg._u2.setText(self._credentials[1][0])
            dlg._p2.setText(self._credentials[1][1])
        if dlg.exec_() == QDialog.Accepted:
            self._credentials = dlg.credentials()

    def _scan_ip_manual(self):
        """Scan one or more explicitly-entered IPs (different subnet support)."""
        raw = self._ip_edit.text().strip()
        if not raw:
            return
        # parse comma / space / newline separated IPs and optional ranges like 192.168.254.1-10
        ips: list[str] = []
        for token in raw.replace(",", " ").replace(";", " ").split():
            if "-" in token:
                # handle range: 192.168.254.1-20
                try:
                    prefix, end_part = token.rsplit(".", 1)
                    start_end = end_part.split("-")
                    start, end = int(start_end[0]), int(start_end[1])
                    for i in range(start, end + 1):
                        ips.append(f"{prefix}.{i}")
                except Exception:
                    ips.append(token)
            else:
                ips.append(token)

        if not ips:
            return

        self._clear_grid()
        self._selected_url = ""
        self._selected_ip  = ""
        self._btn_use.setEnabled(False)
        self._btn_save.setEnabled(False)
        self._detail_lbl.setText("No camera selected")

        self._scanner = RTSPScanner(
            credentials  = self._credentials,
            explicit_ips = ips,
        )
        self._scanner.camera_found.connect(self._on_camera_found)
        self._scanner.progress.connect(self._on_progress)
        self._scanner.finished_scan.connect(self._on_finished)
        self._scanner.start()

        self._btn_scan.setEnabled(False)
        self._btn_scan_ip.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._progress.setFormat(f"Scanning {len(ips)} IP(s)…")

    def _start_scan(self):
        self._clear_grid()
        self._selected_url = ""
        self._selected_ip  = ""
        self._btn_use.setEnabled(False)
        self._btn_save.setEnabled(False)
        self._detail_lbl.setText("No camera selected")

        self._scanner = RTSPScanner(credentials=self._credentials)
        self._scanner.camera_found.connect(self._on_camera_found)
        self._scanner.progress.connect(self._on_progress)
        self._scanner.finished_scan.connect(self._on_finished)
        self._scanner.start()

        self._btn_scan.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._progress.setFormat("Scanning…")

    def _stop_scan(self):
        if self._scanner:
            self._scanner.stop()
        self._btn_scan.setEnabled(True)
        self._btn_scan_ip.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._progress.setFormat("Stopped")

    def _clear_grid(self):
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

    # ── slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(str, str, QImage)
    def _on_camera_found(self, ip: str, url: str, preview: QImage):
        card = _CameraCard(ip, url, preview)
        card.selected.connect(self._on_card_selected)
        idx  = len(self._cards)
        row, col = divmod(idx, self.COLS)
        self._grid_layout.addWidget(card, row, col)
        self._cards.append(card)
        self._status_lbl.setText(f"Found {len(self._cards)} camera(s) so far…")

    @pyqtSlot(int, int, str)
    def _on_progress(self, current: int, total: int, label: str):
        if total > 0:
            pct = int(current * 100 / total)
            self._progress.setValue(pct)
            self._progress.setFormat(f"{label}  ({current}/{total})")

    @pyqtSlot(int)
    def _on_finished(self, count: int):
        self._btn_scan.setEnabled(True)
        self._btn_scan_ip.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._progress.setValue(100)
        self._progress.setFormat(f"Scan complete — {count} camera(s) found")
        self._status_lbl.setText(f"✅  Scan finished.  {count} camera(s) found.")

    @pyqtSlot(str, str)
    def _on_card_selected(self, ip: str, url: str):
        # deselect previous
        for card in self._cards:
            card.set_selected(card.ip == ip and card.url == url)
        self._selected_ip  = ip
        self._selected_url = url
        self._btn_use.setEnabled(True)
        self._btn_save.setEnabled(True)
        short = url.split("@")[-1] if "@" in url else url
        self._detail_lbl.setText(f"Selected:  {ip}   —   {short}")

    # ── use / save ────────────────────────────────────────────────────────────

    def _use_selected(self):
        if self._selected_url:
            self.camera_selected.emit(self._selected_ip, self._selected_url)
            QMessageBox.information(
                self, "Camera Selected",
                f"Camera {self._selected_ip} set as active source.\n\n"
                f"Go to Dashboard and press START.",
            )

    def _save_selected(self):
        if not self._selected_url:
            return
        self._cfg["camera_source"] = self._selected_url
        # also keep in rtsp_profiles list
        profiles: list[dict] = self._cfg.get("rtsp_profiles", [])
        exists = any(p.get("url") == self._selected_url for p in profiles)
        if not exists:
            profiles.append({
                "name":     f"Camera {self._selected_ip}",
                "ip":       self._selected_ip,
                "url":      self._selected_url,
            })
            self._cfg["rtsp_profiles"] = profiles
        ConfigManager().save(self._cfg)

        # persist as a reusable RTSP Profile (shows up on the RTSP Profile page)
        profile = self._url_to_profile(self._selected_url, self._selected_ip)
        RTSPProfileManager().save(profile)

        QMessageBox.information(
            self, "Saved",
            f"Camera saved as RTSP Profile \u201C{profile.name}\u201D.\n"
            f"You can pick it later on the RTSP Profile page.\n\n"
            f"URL: {self._selected_url}",
        )

    def _url_to_profile(self, url: str, ip: str) -> RTSPProfile:
        """Parse an rtsp://user:pwd@host:port/path URL into an RTSPProfile."""
        parsed = urlparse(url)
        host = parsed.hostname or ip
        port = parsed.port or 554
        user = unquote(parsed.username) if parsed.username else ""
        pwd  = unquote(parsed.password) if parsed.password else ""
        path = parsed.path or ""
        if parsed.query:
            path = f"{path}?{parsed.query}"

        # build a unique, human-friendly profile name
        base = f"Camera {host}"
        name = base
        mgr  = RTSPProfileManager()
        existing = {p.name for p in mgr.list_all()}
        i = 2
        while name in existing:
            name = f"{base} ({i})"
            i += 1

        return RTSPProfile(
            name     = name,
            host     = host,
            port     = port,
            path     = path,
            username = user,
            password = pwd,
        )
