"""Notification page — Teams webhook config."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QGroupBox, QFormLayout,
)
from PyQt5.QtCore import pyqtSlot
from notification.teams_notifier import TeamsNotifier
from config.config_manager       import ConfigManager


class NotificationPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        title = QLabel("Notification"); title.setObjectName("PageTitle")
        root.addWidget(title)

        wh_group = QGroupBox("Microsoft Teams Webhook")
        form     = QFormLayout(wh_group)
        self._enable_chk     = QCheckBox("Enable webhook notifications")
        self._url_edit       = QLineEdit()
        self._url_edit.setPlaceholderText("https://xxxx.webhook.office.com/webhookb2/…")
        self._send_pass_chk  = QCheckBox("Send on PASS")
        self._send_fail_chk  = QCheckBox("Send on FAIL")
        form.addRow(self._enable_chk)
        form.addRow("Webhook URL:", self._url_edit)
        form.addRow(self._send_pass_chk)
        form.addRow(self._send_fail_chk)
        root.addWidget(wh_group)

        test_row = QHBoxLayout()
        btn_test = QPushButton("📨  Send Test")
        btn_test.clicked.connect(self._test)
        self._test_lbl = QLabel(""); self._test_lbl.setStyleSheet("color:#5A8ABF;")
        test_row.addWidget(btn_test); test_row.addWidget(self._test_lbl); test_row.addStretch()
        root.addLayout(test_row)
        root.addStretch()

        btn_save = QPushButton("💾  Save"); btn_save.setObjectName("SuccessButton")
        btn_save.clicked.connect(self._save)
        root.addWidget(btn_save)

    def _load(self):
        self._enable_chk.setChecked(bool(self._cfg.get("teams_webhook", "")))
        self._url_edit.setText(self._cfg.get("teams_webhook", ""))
        self._send_pass_chk.setChecked(self._cfg.get("teams_send_pass", False))
        self._send_fail_chk.setChecked(self._cfg.get("teams_send_fail", True))

    @pyqtSlot()
    def _save(self):
        self._cfg["teams_webhook"]   = self._url_edit.text().strip() if self._enable_chk.isChecked() else ""
        self._cfg["teams_send_pass"] = self._send_pass_chk.isChecked()
        self._cfg["teams_send_fail"] = self._send_fail_chk.isChecked()
        ConfigManager().save(self._cfg)
        self._test_lbl.setText("✔ Saved")

    @pyqtSlot()
    def _test(self):
        notifier = TeamsNotifier(webhook_url=self._url_edit.text().strip())
        ok, msg  = notifier.test()
        self._test_lbl.setText(f"{'✔' if ok else '✘'} {msg}")
        self._test_lbl.setStyleSheet(f"color:{'#00C853' if ok else '#FF1744'};")
