"""Calibration page — interactive crossing line drawing."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy,
)
from PyQt5.QtCore  import Qt, QPoint, QTimer
from PyQt5.QtGui   import QPixmap, QImage, QPainter, QPen, QColor

import cv2

from camera.camera_manager import CameraManager
from detection.crossing_line import CrossingLine
from config.config_manager   import ConfigManager


class _PreviewLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#0D1B2A; border-radius:4px;")
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._p1 = self._p2 = None
        self._drawing = False

    def start_draw(self):
        self._p1 = self._p2 = None
        self._drawing = True
        self.setCursor(Qt.CrossCursor)

    def clear_line(self):
        self._p1 = self._p2 = None
        self._drawing = False
        self.setCursor(Qt.ArrowCursor)

    def has_line(self):
        return self._p1 is not None and self._p2 is not None

    def get_line(self):
        if not self.has_line():
            return None, None
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return None, None
        ox = (self.width()  - pm.width())  // 2
        oy = (self.height() - pm.height()) // 2
        return (self._p1.x() - ox, self._p1.y() - oy), (self._p2.x() - ox, self._p2.y() - oy)

    def mousePressEvent(self, event):
        if not self._drawing:
            return
        if event.button() == Qt.LeftButton:
            if self._p1 is None:
                self._p1 = event.pos()
            else:
                self._p2 = event.pos()
                self._drawing = False
                self.setCursor(Qt.ArrowCursor)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._p1 is None:
            return
        p = QPainter(self)
        p.setPen(QPen(QColor(0, 220, 255), 2))
        p.drawEllipse(self._p1, 5, 5)
        if self._p2:
            p.drawLine(self._p1, self._p2)
            p.drawEllipse(self._p2, 5, 5)


class CalibrationPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg    = cfg
        self._camera = CameraManager()
        self._timer  = QTimer()
        self._timer.timeout.connect(self._tick)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("Calibration — Crossing Line")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        info = QLabel("1. Start Preview  2. Click Draw Line and click two points  3. Save")
        info.setStyleSheet("color:#5A8ABF;")
        root.addWidget(info)

        self._preview = _PreviewLabel()
        root.addWidget(self._preview, stretch=1)

        ctrl = QHBoxLayout()
        self._btn_preview = QPushButton("▶  Start Preview")
        self._btn_preview.setObjectName("SuccessButton")
        self._btn_preview.clicked.connect(self._start_preview)

        self._btn_stop = QPushButton("■  Stop")
        self._btn_stop.clicked.connect(self._stop_preview)
        self._btn_stop.setEnabled(False)

        self._btn_draw = QPushButton("✏  Draw Line")
        self._btn_draw.clicked.connect(self._draw_line)
        self._btn_draw.setEnabled(False)

        self._btn_clear = QPushButton("✕  Clear")
        self._btn_clear.clicked.connect(self._clear_line)

        self._btn_save = QPushButton("💾  Save")
        self._btn_save.setObjectName("SuccessButton")
        self._btn_save.clicked.connect(self._save)
        self._btn_save.setEnabled(False)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#5A8ABF;")

        for w in (self._btn_preview, self._btn_stop, self._btn_draw,
                  self._btn_clear, self._btn_save, self._status_lbl):
            ctrl.addWidget(w)
        ctrl.addStretch()
        root.addLayout(ctrl)

    def _start_preview(self):
        if self._camera.connect(self._cfg.get("camera_source", 0)):
            self._timer.start(33)
            self._btn_preview.setEnabled(False)
            self._btn_stop.setEnabled(True)
            self._btn_draw.setEnabled(True)
            self._status_lbl.setText("Camera connected")
        else:
            self._status_lbl.setText("Cannot open camera")

    def _stop_preview(self):
        self._timer.stop()
        self._camera.disconnect()
        self._btn_preview.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._btn_draw.setEnabled(False)

    def _tick(self):
        frame = self._camera.read()
        if frame is None:
            return
        frame = cv2.flip(frame, 1)
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(img).scaled(
            self._preview.width(), self._preview.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._preview.setPixmap(pix)

    def _draw_line(self):
        self._preview.start_draw()
        self._status_lbl.setText("Click first point…")
        self._btn_save.setEnabled(True)

    def _clear_line(self):
        self._preview.clear_line()
        self._cfg["crossing_line"] = None
        self._status_lbl.setText("Line cleared")
        self._btn_save.setEnabled(False)

    def _save(self):
        p1, p2 = self._preview.get_line()
        if p1 and p2:
            self._cfg["crossing_line"] = {"p1": list(p1), "p2": list(p2)}
            ConfigManager().save(self._cfg)
            self._status_lbl.setText("✔ Crossing line saved")
        else:
            self._status_lbl.setText("Draw a line first")
