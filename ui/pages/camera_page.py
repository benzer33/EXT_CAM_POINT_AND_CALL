"""Camera page — source selection + RTSP profile manager."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox,
    QMessageBox, QFileDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot

from camera.camera_manager  import CameraManager
from camera.rtsp_profiles   import RTSPProfile, RTSPProfileManager


class _ProfileDialog(QDialog):
    def __init__(self, profile: RTSPProfile | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RTSP Profile")
        form = QFormLayout(self)
        self._name = QLineEdit(profile.name     if profile else "")
        self._host = QLineEdit(profile.host     if profile else "")
        self._port = QSpinBox(); self._port.setRange(1, 65535); self._port.setValue(profile.port if profile else 554)
        self._path = QLineEdit(profile.path     if profile else "")
        self._user = QLineEdit(profile.username if profile else "")
        self._pwd  = QLineEdit(profile.password if profile else "")
        self._pwd.setEchoMode(QLineEdit.Password)
        form.addRow("Profile Name:", self._name)
        form.addRow("Host / IP:",    self._host)
        form.addRow("Port:",         self._port)
        form.addRow("Path:",         self._path)
        form.addRow("Username:",     self._user)
        form.addRow("Password:",     self._pwd)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def get_profile(self) -> RTSPProfile:
        return RTSPProfile(
            name=self._name.text().strip(),
            host=self._host.text().strip(),
            port=self._port.value(),
            path=self._path.text().strip(),
            username=self._user.text().strip(),
            password=self._pwd.text(),
        )


class CameraPage(QWidget):
    camera_connected = pyqtSignal(object)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg      = cfg
        self._camera   = CameraManager()
        self._profiles = RTSPProfileManager()
        self._build_ui()
        self._load_profiles()

    def showEvent(self, event):
        """Refresh the profile table each time the page becomes visible."""
        super().showEvent(event)
        self._load_profiles()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("Camera")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        # source row
        src_row = QHBoxLayout()
        self._src_combo = QComboBox()
        self._src_combo.addItems(["Webcam 0", "Webcam 1", "Video File…", "RTSP URL…"])
        self._src_combo.currentIndexChanged.connect(self._on_src_changed)
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("rtsp://… or file path")
        self._url_edit.setVisible(False)
        btn_file = QPushButton("Browse…")
        btn_file.setVisible(False)
        btn_file.clicked.connect(self._browse_file)
        self._btn_file = btn_file

        self._btn_connect    = QPushButton("🔌  Connect")
        self._btn_connect.setObjectName("SuccessButton")
        self._btn_connect.clicked.connect(self._connect)
        self._btn_disconnect = QPushButton("✕  Disconnect")
        self._btn_disconnect.clicked.connect(self._disconnect)
        self._btn_disconnect.setEnabled(False)
        self._status_lbl = QLabel("Not connected")
        self._status_lbl.setStyleSheet("color:#5A8ABF;")

        for w in (self._src_combo, self._url_edit, btn_file,
                  self._btn_connect, self._btn_disconnect, self._status_lbl):
            src_row.addWidget(w)
        src_row.addStretch()
        root.addLayout(src_row)

        # RTSP profiles table
        prof_lbl = QLabel("RTSP Profiles")
        prof_lbl.setStyleSheet("color:#5A8ABF; font-weight:bold;")
        root.addWidget(prof_lbl)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Name", "Host", "Port", "Path"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self._table, stretch=1)

        btn_row = QHBoxLayout()
        for label, slot in [("➕ Add", self._add_profile),
                             ("✏ Edit", self._edit_profile),
                             ("✕ Delete", self._delete_profile),
                             ("▶ Use Profile", self._use_profile)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        root.addLayout(btn_row)

    def _on_src_changed(self, idx: int):
        is_custom = idx >= 2
        self._url_edit.setVisible(is_custom)
        self._btn_file.setVisible(idx == 2)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Video File")
        if path:
            self._url_edit.setText(path)

    def _get_source(self):
        idx = self._src_combo.currentIndex()
        if idx == 0:
            return 0
        if idx == 1:
            return 1
        return self._url_edit.text().strip()

    def _connect(self):
        source = self._get_source()
        if self._camera.connect(source):
            self._cfg["camera_source"] = source
            self._status_lbl.setText(f"✔ Connected: {source}")
            self._status_lbl.setStyleSheet("color:#00C853;")
            self._btn_connect.setEnabled(False)
            self._btn_disconnect.setEnabled(True)
            self.camera_connected.emit(source)
        else:
            self._status_lbl.setText("✘ Failed to connect")
            self._status_lbl.setStyleSheet("color:#FF1744;")

    def _disconnect(self):
        self._camera.disconnect()
        self._status_lbl.setText("Disconnected")
        self._status_lbl.setStyleSheet("color:#5A8ABF;")
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)

    def _load_profiles(self):
        self._table.setRowCount(0)
        for p in self._profiles.list_all():
            r = self._table.rowCount()
            self._table.insertRow(r)
            for c, v in enumerate([p.name, p.host, str(p.port), p.path]):
                self._table.setItem(r, c, QTableWidgetItem(v))

    def _add_profile(self):
        dlg = _ProfileDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            p = dlg.get_profile()
            if p.name:
                self._profiles.save(p)
                self._load_profiles()

    def _edit_profile(self):
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        p    = self._profiles.get(name)
        dlg  = _ProfileDialog(p, self)
        if dlg.exec_() == QDialog.Accepted:
            self._profiles.save(dlg.get_profile())
            self._load_profiles()

    def _delete_profile(self):
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        if QMessageBox.question(self, "Delete", f"Delete profile '{name}'?") == QMessageBox.Yes:
            self._profiles.delete(name)
            self._load_profiles()

    def _use_profile(self):
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        p    = self._profiles.get(name)
        if p:
            url = p.get_connection_url()
            self._src_combo.setCurrentIndex(3)
            self._url_edit.setText(url)
            self._connect()
