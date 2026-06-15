"""Settings page — device/model selection + general settings."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QCheckBox, QGroupBox, QFormLayout,
    QFileDialog, QComboBox, QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSlot, QThread, pyqtSignal
from config.config_manager import ConfigManager


class _ProbeThread(QThread):
    done = pyqtSignal(list, str, str)

    def run(self):
        from utils.device_check import list_devices, install_command_for_gpu, torch_info
        devices = list_devices()
        cmd     = install_command_for_gpu()
        info    = torch_info(force_refresh=True)
        raw_err = info.get("error") or info.get("cuda_error") or ""
        self.done.emit(devices, cmd, raw_err)


class SettingsPage(QWidget):
    config_saved = pyqtSignal(dict)   # emitted after _save(), carries updated cfg

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg     = cfg
        self._devices = [{"value": "cpu", "label": "CPU  (always available)"}]
        self._install_cmd = ""
        self._build_ui()
        self._load()
        self._probe_devices()

    def _build_ui(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        inner  = QWidget()
        root   = QVBoxLayout(inner)
        root.setContentsMargins(20, 20, 20, 20); root.setSpacing(16)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)

        title = QLabel("Settings"); title.setObjectName("PageTitle")
        root.addWidget(title)

        # ── device ────────────────────────────────────────────────────────────
        dev_group = QGroupBox("Inference Device  (CPU / GPU)")
        dev_vbox  = QVBoxLayout(dev_group)

        self._device_combo = QComboBox()
        self._device_combo.addItem("CPU  (always available)", "cpu")
        dev_vbox.addWidget(self._device_combo)

        self._device_status_lbl = QLabel("Scanning devices…")
        self._device_status_lbl.setStyleSheet("color:#5A8ABF; font-size:11px;")
        dev_vbox.addWidget(self._device_status_lbl)

        self._install_box = QGroupBox("Fix: reinstall PyTorch for your GPU")
        self._install_box.setVisible(False)
        ibox_vbox = QVBoxLayout(self._install_box)
        self._install_info = QLabel()
        self._install_info.setWordWrap(True)
        self._install_info.setStyleSheet("color:#FFA726;")
        ibox_vbox.addWidget(self._install_info)
        cmd_row = QHBoxLayout()
        self._install_cmd_edit = QLineEdit(); self._install_cmd_edit.setReadOnly(True)
        self._install_cmd_edit.setStyleSheet("font-family:Consolas,monospace; font-size:11px;")
        btn_copy = QPushButton("Copy"); btn_copy.setFixedWidth(60); btn_copy.clicked.connect(self._copy_cmd)
        cmd_row.addWidget(self._install_cmd_edit); cmd_row.addWidget(btn_copy)
        ibox_vbox.addLayout(cmd_row)
        dev_vbox.addWidget(self._install_box)

        btn_rescan = QPushButton("↻  Rescan Devices"); btn_rescan.clicked.connect(self._probe_devices)
        dev_vbox.addWidget(btn_rescan)
        root.addWidget(dev_group)

        # ── model ─────────────────────────────────────────────────────────────
        model_group = QGroupBox("YOLO Model")
        model_form  = QFormLayout(model_group)
        self._model_combo = QComboBox()
        _MODELS = [
            ("yolov8n-pose.pt", "YOLOv8n-pose  (Nano  — fastest)"),
            ("yolov8s-pose.pt", "YOLOv8s-pose  (Small — fast)"),
            ("yolov8m-pose.pt", "YOLOv8m-pose  (Medium)"),
            ("yolov8l-pose.pt", "YOLOv8l-pose  (Large — accurate)"),
            ("yolov8x-pose.pt", "YOLOv8x-pose  (XLarge — most accurate)"),
            ("yolo11n-pose.pt", "YOLO11n-pose  (Nano  latest)"),
            ("yolo11s-pose.pt", "YOLO11s-pose  (Small latest)"),
            ("yolo11m-pose.pt", "YOLO11m-pose  (Medium latest)"),
            ("yolo11l-pose.pt", "YOLO11l-pose  (Large latest)"),
            ("yolo11x-pose.pt", "YOLO11x-pose  (XLarge latest)"),
        ]
        for val, lbl in _MODELS:
            self._model_combo.addItem(lbl, val)
        model_form.addRow("Model:", self._model_combo)
        note = QLabel("Models auto-download on first use.\nNano/Small run on CPU; Medium+ benefit from GPU.")
        note.setWordWrap(True); note.setStyleSheet("color:#5A8ABF; font-size:11px;")
        model_form.addRow(note)
        root.addWidget(model_group)

        # ── general ───────────────────────────────────────────────────────────
        gen_group = QGroupBox("General"); form = QFormLayout(gen_group)
        self._auto_connect_chk = QCheckBox("Auto connect camera on start")
        self._auto_start_chk   = QCheckBox("Auto start monitoring on launch")
        form.addRow(self._auto_connect_chk); form.addRow(self._auto_start_chk)
        root.addWidget(gen_group)

        # ── image storage ─────────────────────────────────────────────────────
        img_group = QGroupBox("Image Storage"); img_form = QFormLayout(img_group)
        self._save_img_chk = QCheckBox("Save capture images on crossing event")
        img_form.addRow(self._save_img_chk)
        cap_row = QHBoxLayout()
        self._capture_dir_edit = QLineEdit(); self._capture_dir_edit.setReadOnly(True)
        btn_browse = QPushButton("Browse…"); btn_browse.clicked.connect(self._browse_capture)
        cap_row.addWidget(self._capture_dir_edit); cap_row.addWidget(btn_browse)
        img_form.addRow("Capture Folder:", cap_row)
        self._retention_spin = QSpinBox(); self._retention_spin.setRange(1, 365); self._retention_spin.setSuffix(" days")
        img_form.addRow("Delete older than:", self._retention_spin)
        root.addWidget(img_group)

        # ── database ──────────────────────────────────────────────────────────
        db_group = QGroupBox("MSSQL Database"); db_form = QFormLayout(db_group)
        self._db_server   = QLineEdit(); self._db_database = QLineEdit()
        self._db_user     = QLineEdit()
        self._db_pass     = QLineEdit(); self._db_pass.setEchoMode(QLineEdit.Password)
        self._db_driver   = QLineEdit()
        db_form.addRow("Server:",   self._db_server)
        db_form.addRow("Database:", self._db_database)
        db_form.addRow("Username:", self._db_user)
        db_form.addRow("Password:", self._db_pass)
        db_form.addRow("Driver:",   self._db_driver)
        db_test_row = QHBoxLayout()
        btn_db_test = QPushButton("🔌  Test Connection"); btn_db_test.clicked.connect(self._test_db)
        self._db_status_lbl = QLabel(""); self._db_status_lbl.setStyleSheet("color:#5A8ABF;")
        db_test_row.addWidget(btn_db_test); db_test_row.addWidget(self._db_status_lbl); db_test_row.addStretch()
        db_form.addRow(db_test_row)
        root.addWidget(db_group)
        root.addStretch()

        btn_save = QPushButton("💾  Save All Settings"); btn_save.setObjectName("SuccessButton")
        btn_save.clicked.connect(self._save)
        root.addWidget(btn_save)

    # ── device probe ──────────────────────────────────────────────────────────
    def _probe_devices(self):
        self._device_status_lbl.setText("Scanning devices…")
        self._thread = _ProbeThread()
        self._thread.done.connect(self._on_probe_done)
        self._thread.start()

    @pyqtSlot(list, str, str)
    def _on_probe_done(self, devices, install_cmd, raw_error):
        self._devices = devices; self._install_cmd = install_cmd
        saved = self._cfg.get("device", "cpu")
        self._device_combo.blockSignals(True); self._device_combo.clear()
        for d in devices:
            self._device_combo.addItem(d["label"], d["value"])
        for i in range(self._device_combo.count()):
            if self._device_combo.itemData(i) == saved:
                self._device_combo.setCurrentIndex(i); break
        self._device_combo.blockSignals(False)

        gpu_found = any(d["value"] != "cpu" for d in devices)
        if gpu_found:
            self._device_status_lbl.setText(f"✔  {len(devices)-1} GPU(s) detected — CUDA working.")
            self._device_status_lbl.setStyleSheet("color:#00C853; font-size:11px;")
            self._install_box.setVisible(False)
        else:
            self._device_status_lbl.setText("⚠  No CUDA GPU detected.")
            self._device_status_lbl.setStyleSheet("color:#FFA726; font-size:11px;")
            self._install_info.setText(
                (f"Error: {raw_error[:200]}\n\n" if raw_error else "") +
                "Run the command below to fix, then restart:"
            )
            self._install_cmd_edit.setText(install_cmd)
            self._install_box.setVisible(True)

    def _copy_cmd(self):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self._install_cmd_edit.text())

    # ── load / save ───────────────────────────────────────────────────────────
    def _load(self):
        saved_model = self._cfg.get("yolo_model", "yolov8n-pose.pt")
        for i in range(self._model_combo.count()):
            if self._model_combo.itemData(i) == saved_model:
                self._model_combo.setCurrentIndex(i); break

        self._auto_connect_chk.setChecked(self._cfg.get("auto_connect", False))
        self._auto_start_chk.setChecked(  self._cfg.get("auto_start",   False))
        self._save_img_chk.setChecked(    self._cfg.get("save_images",   True))
        self._capture_dir_edit.setText(   self._cfg.get("capture_dir",   "captures"))
        self._retention_spin.setValue(    self._cfg.get("retention_days", 30))
        mssql = self._cfg.get("mssql", {})
        self._db_server.setText(  mssql.get("server",   ""))
        self._db_database.setText(mssql.get("database", ""))
        self._db_user.setText(    mssql.get("username", ""))
        self._db_pass.setText(    mssql.get("password", ""))
        self._db_driver.setText(  mssql.get("driver",   "ODBC Driver 17 for SQL Server"))

    @pyqtSlot()
    def _browse_capture(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Capture Folder")
        if folder:
            self._capture_dir_edit.setText(folder)

    @pyqtSlot()
    def _test_db(self):
        from database.db_manager import DBManager
        ok = DBManager({"server": self._db_server.text(), "database": self._db_database.text(),
                        "username": self._db_user.text(), "password": self._db_pass.text(),
                        "driver": self._db_driver.text()}).init()
        self._db_status_lbl.setText("✔ Connected" if ok else "✘ Failed")
        self._db_status_lbl.setStyleSheet(f"color:{'#00C853' if ok else '#FF1744'};")

    @pyqtSlot()
    def _save(self):
        self._cfg["device"]       = self._device_combo.currentData() or "cpu"
        self._cfg["yolo_model"]   = self._model_combo.currentData()  or "yolov8n-pose.pt"
        self._cfg["auto_connect"] = self._auto_connect_chk.isChecked()
        self._cfg["auto_start"]   = self._auto_start_chk.isChecked()
        self._cfg["save_images"]  = self._save_img_chk.isChecked()
        self._cfg["capture_dir"]  = self._capture_dir_edit.text()
        self._cfg["retention_days"] = self._retention_spin.value()
        self._cfg["mssql"] = {
            "server":   self._db_server.text().strip(),
            "database": self._db_database.text().strip(),
            "username": self._db_user.text().strip(),
            "password": self._db_pass.text(),
            "driver":   self._db_driver.text().strip(),
        }
        ConfigManager().save(self._cfg)
        self._db_status_lbl.setText("✔ Saved")
        self._db_status_lbl.setStyleSheet("color:#00C853;")
        self.config_saved.emit(self._cfg)
