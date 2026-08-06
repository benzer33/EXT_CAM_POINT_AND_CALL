"""Detection Settings page — sensitivity, thresholds, false-positive suppression, overlay toggle."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QGroupBox, QRadioButton, QDoubleSpinBox,
    QFormLayout, QSpinBox, QCheckBox, QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSlot
from config.config_manager import ConfigManager


class DetectionPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self._load()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        root  = QVBoxLayout(inner)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        title = QLabel("Detection Settings")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        # ── sensitivity ───────────────────────────────────────────────────────
        sens_group = QGroupBox("Sensitivity Mode")
        sens_vbox  = QVBoxLayout(sens_group)
        self._rb_strict   = QRadioButton("Strict   —  requires correct order R → L → S, wrist must reach threshold")
        self._rb_handsup  = QRadioButton("Handsup  —  ยกมือสองข้างขึ้นเหนือเอว (LEFT → RIGHT → HANDSUP)")
        self._rb_loose    = QRadioButton("Loose    —  any order, no height requirement (L + R only)")
        for rb in (self._rb_strict, self._rb_handsup, self._rb_loose):
            sens_vbox.addWidget(rb)
        root.addWidget(sens_group)

        # ── overlay toggle ────────────────────────────────────────────────────
        vis_group = QGroupBox("Visualisation")
        vis_vbox  = QVBoxLayout(vis_group)
        self._overlay_chk = QCheckBox("Show shoulder reference lines and wrist dots on live feed")
        vis_vbox.addWidget(self._overlay_chk)
        root.addWidget(vis_group)

        # ── advanced parameters ───────────────────────────────────────────────
        adv_group = QGroupBox("Advanced Parameters")
        form = QFormLayout(adv_group)
        form.setLabelAlignment(Qt.AlignLeft)

        def spin(lo, hi, step, dec, suffix=""):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setSingleStep(step)
            s.setDecimals(dec)
            s.setFixedWidth(130)
            if suffix:
                s.setSuffix(suffix)
            return s

        self._conf_spin     = spin(0.10, 1.00, 0.05, 2)
        self._hold_spin     = spin(0.10, 3.00, 0.10, 1, " s")
        self._cooldown_spin = spin(1.00, 120.0, 1.0, 0, " s")
        self._side_spin     = spin(0.01, 0.50, 0.01, 2)
        self._height_spin   = spin(0.10, 1.00, 0.05, 2)
        self._center_spin   = spin(0.01, 0.50, 0.01, 2)

        form.addRow("YOLO Confidence:",       self._conf_spin)
        form.addRow("Hold Time:",             self._hold_spin)
        form.addRow("Log Cooldown:",          self._cooldown_spin)
        form.addRow("Side Ratio:",            self._side_spin)
        form.addRow("Height Ratio:",          self._height_spin)
        form.addRow("Center Ratio (STRAIGHT):", self._center_spin)
        root.addWidget(adv_group)

        # ── false-positive suppression ────────────────────────────────────────
        fp_group = QGroupBox("False-Positive Suppression")
        fp_form  = QFormLayout(fp_group)

        note = QLabel(
            "Partial / edge detections are ignored until a track has been visible\n"
            "for the minimum frames and the bounding box is large enough."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#5A8ABF; font-size:11px;")
        fp_form.addRow(note)

        self._min_frames_spin = QSpinBox()
        self._min_frames_spin.setRange(1, 60)
        self._min_frames_spin.setSuffix(" frames")
        self._min_frames_spin.setFixedWidth(130)

        self._min_bbox_h_spin = spin(0.01, 0.80, 0.01, 2, " × H")
        self._min_bbox_w_spin = spin(0.01, 0.80, 0.01, 2, " × W")

        fp_form.addRow("Min visible frames:", self._min_frames_spin)
        fp_form.addRow("Min bbox height:",    self._min_bbox_h_spin)
        fp_form.addRow("Min bbox width:",     self._min_bbox_w_spin)
        root.addWidget(fp_group)
        root.addStretch()

        btn_save = QPushButton("💾  Save Settings")
        btn_save.setObjectName("SuccessButton")
        btn_save.clicked.connect(self._save)
        root.addWidget(btn_save)

    def _load(self):
        mode = self._cfg.get("sensitivity", "STRICT")
        self._rb_strict.setChecked(  mode == "STRICT")
        self._rb_handsup.setChecked( mode == "HANDSUP")
        self._rb_loose.setChecked(   mode == "LOOSE")
        self._overlay_chk.setChecked(self._cfg.get("show_debug_overlay", True))
        self._conf_spin.setValue(    self._cfg.get("conf_threshold",    0.50))
        self._hold_spin.setValue(    self._cfg.get("hold_seconds",      0.30))
        self._cooldown_spin.setValue(self._cfg.get("log_cooldown",     10.0))
        self._side_spin.setValue(    self._cfg.get("side_ratio",        0.05))
        self._height_spin.setValue(  self._cfg.get("height_ratio",     0.40))
        self._center_spin.setValue(  self._cfg.get("center_ratio",     0.10))
        self._min_frames_spin.setValue(self._cfg.get("min_visible_frames",  8))
        self._min_bbox_h_spin.setValue(self._cfg.get("min_bbox_height_rel", 0.15))
        self._min_bbox_w_spin.setValue(self._cfg.get("min_bbox_width_rel",  0.05))

    @pyqtSlot()
    def _save(self):
        if self._rb_strict.isChecked():
            self._cfg["sensitivity"] = "STRICT"
        elif self._rb_handsup.isChecked():
            self._cfg["sensitivity"] = "HANDSUP"
        else:
            self._cfg["sensitivity"] = "LOOSE"

        self._cfg["show_debug_overlay"]  = self._overlay_chk.isChecked()
        self._cfg["conf_threshold"]      = self._conf_spin.value()
        self._cfg["hold_seconds"]        = self._hold_spin.value()
        self._cfg["log_cooldown"]        = self._cooldown_spin.value()
        self._cfg["side_ratio"]          = self._side_spin.value()
        self._cfg["height_ratio"]        = self._height_spin.value()
        self._cfg["center_ratio"]        = self._center_spin.value()
        self._cfg["min_visible_frames"]  = self._min_frames_spin.value()
        self._cfg["min_bbox_height_rel"] = self._min_bbox_h_spin.value()
        self._cfg["min_bbox_width_rel"]  = self._min_bbox_w_spin.value()
        ConfigManager().save(self._cfg)
