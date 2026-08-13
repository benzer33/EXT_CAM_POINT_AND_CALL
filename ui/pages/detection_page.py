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
        self._rb_strict   = QRadioButton("Strict   —  เข้มงวด ต้องชี้ขวา ซ้าย ตรง ตามลำดับ แนวหัวไหล่")
        self._rb_handsup  = QRadioButton("Handsup  —  ยกมือสองข้างขึ้นเหนือเอว (LEFT → RIGHT → HANDSUP)")
        self._rb_loose    = QRadioButton("Loose    —  แค่โยกซ้ายโยกขวา สูงระดับใดก็ได้ ก็ผ่านแล้ว")
        for rb in (self._rb_strict, self._rb_handsup, self._rb_loose):
            sens_vbox.addWidget(rb)
        root.addWidget(sens_group)

        # ── overlay toggle ────────────────────────────────────────────────────
        handsup_level_group = QGroupBox("Handsup Level")
        hl_vbox = QVBoxLayout(handsup_level_group)
        self._rb_level_waist    = QRadioButton("Waist    —  ยกมือเหนือระดับเอว (ค่าเดิม)")
        self._rb_level_chest    = QRadioButton("Chest    —  ยกมือเหนือระดับหน้าอก (ประมาณจากกึ่งกลางไหล่-เอว)")
        self._rb_level_shoulder = QRadioButton("Shoulder —  ยกมือเหนือระดับไหล่ (เข้มงวดสุด)")
        for rb in (self._rb_level_waist, self._rb_level_chest, self._rb_level_shoulder):
            hl_vbox.addWidget(rb)
        root.addWidget(handsup_level_group)

        vis_group = QGroupBox("Visualisation")
        vis_vbox  = QVBoxLayout(vis_group)
        self._overlay_chk = QCheckBox("แสดงเส้นอ้างอิงไหล่และจุดข้อมือบนฟีดสด")
        self._require_face_chk = QCheckBox(
            "นับ PASS/FAIL เฉพาะตอนเจอหน้าคน — คนที่หันหลังให้กล้องจะไม่ถูกนับทั้ง PASS และ FAIL"
        )
        vis_vbox.addWidget(self._overlay_chk)
        vis_vbox.addWidget(self._require_face_chk)
        root.addWidget(vis_group)

        # ── forklift suppression ───────────────────────────────────────────────
        fk_group = QGroupBox("Forklift Suppression")
        fk_vbox  = QVBoxLayout(fk_group)
        self._forklift_suppress_chk = QCheckBox(
            "ไม่นับ PASS/FAIL สำหรับคนที่กำลังขับโฟล์คลิฟท์ "
            "(ต้องมีไฟล์โมเดล models/forklift_best.pt ก่อนเปิดใช้งาน)"
        )
        fk_vbox.addWidget(self._forklift_suppress_chk)
        root.addWidget(fk_group)

        # ── direction gate ───────────────────────────────────────────────
        dg_group = QGroupBox("Direction Gate")
        dg_vbox  = QVBoxLayout(dg_group)
        self._direction_gate_chk = QCheckBox(
            "ตรวจทิศทางการเดินก่อนนับ PASS/FAIL — ต้องตั้งโซนตามลำดับ 0-1 > 2-3 "
        )
        dg_vbox.addWidget(self._direction_gate_chk)
        root.addWidget(dg_group)
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

        # ── tracking stability ─────────────────────────────────────────────────
        ts_group = QGroupBox("⛹ Tracking Stability")
        ts_form  = QFormLayout(ts_group)

        ts_note = QLabel(
            "Grace Period: วินาทีรอก่อน log ว่าคนออกจริง\n"
            "(สูงขึ้น = ทนทาน track switching ดีขึ้น)"
        )
        ts_note.setWordWrap(True)
        ts_note.setStyleSheet("color:#5A8ABF; font-size:11px;")
        ts_form.addRow(ts_note)

        self._grace_spin = QDoubleSpinBox()
        self._grace_spin.setRange(0.5, 5.0)
        self._grace_spin.setSingleStep(0.5)
        self._grace_spin.setDecimals(1)
        self._grace_spin.setSuffix(" วินาที")
        self._grace_spin.setFixedWidth(130)

        self._reid_dist_spin = QSpinBox()
        self._reid_dist_spin.setRange(50, 300)
        self._reid_dist_spin.setSingleStep(10)
        self._reid_dist_spin.setSuffix(" px")
        self._reid_dist_spin.setFixedWidth(130)

        ts_form.addRow("Grace Period (วินาที):", self._grace_spin)
        ts_form.addRow("Re-ID Distance (px):",  self._reid_dist_spin)
        root.addWidget(ts_group)
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
        level = self._cfg.get("handsup_level", "waist")
        self._rb_level_waist.setChecked(   level == "waist")
        self._rb_level_chest.setChecked(   level == "chest")
        self._rb_level_shoulder.setChecked(level == "shoulder")
        self._overlay_chk.setChecked(self._cfg.get("show_debug_overlay", True))
        self._require_face_chk.setChecked(self._cfg.get("require_face_to_log", False))
        self._forklift_suppress_chk.setChecked(self._cfg.get("enable_forklift_suppression", False))
        self._direction_gate_chk.setChecked(self._cfg.get("require_direction_gate", False))
        self._conf_spin.setValue(    self._cfg.get("conf_threshold",    0.50))
        self._hold_spin.setValue(    self._cfg.get("hold_seconds",      0.30))
        self._cooldown_spin.setValue(self._cfg.get("log_cooldown",     10.0))
        self._side_spin.setValue(    self._cfg.get("side_ratio",        0.05))
        self._height_spin.setValue(  self._cfg.get("height_ratio",     0.40))
        self._center_spin.setValue(  self._cfg.get("center_ratio",     0.10))
        self._min_frames_spin.setValue(self._cfg.get("min_visible_frames",  8))
        self._min_bbox_h_spin.setValue(self._cfg.get("min_bbox_height_rel", 0.15))
        self._min_bbox_w_spin.setValue(self._cfg.get("min_bbox_width_rel",  0.05))
        self._grace_spin.setValue(     self._cfg.get("track_grace_period_sec",      1.5))
        self._reid_dist_spin.setValue( self._cfg.get("track_reid_max_distance_px", 150))

    @pyqtSlot()
    def _save(self):
        if self._rb_strict.isChecked():
            self._cfg["sensitivity"] = "STRICT"
        elif self._rb_handsup.isChecked():
            self._cfg["sensitivity"] = "HANDSUP"
        else:
            self._cfg["sensitivity"] = "LOOSE"

        if self._rb_level_chest.isChecked():
            self._cfg["handsup_level"] = "chest"
        elif self._rb_level_shoulder.isChecked():
            self._cfg["handsup_level"] = "shoulder"
        else:
            self._cfg["handsup_level"] = "waist"

        self._cfg["show_debug_overlay"]          = self._overlay_chk.isChecked()
        self._cfg["require_face_to_log"]          = self._require_face_chk.isChecked()
        self._cfg["enable_forklift_suppression"]  = self._forklift_suppress_chk.isChecked()
        self._cfg["require_direction_gate"]        = self._direction_gate_chk.isChecked()
        self._cfg["conf_threshold"]      = self._conf_spin.value()
        self._cfg["hold_seconds"]        = self._hold_spin.value()
        self._cfg["log_cooldown"]        = self._cooldown_spin.value()
        self._cfg["side_ratio"]          = self._side_spin.value()
        self._cfg["height_ratio"]        = self._height_spin.value()
        self._cfg["center_ratio"]        = self._center_spin.value()
        self._cfg["min_visible_frames"]  = self._min_frames_spin.value()
        self._cfg["min_bbox_height_rel"] = self._min_bbox_h_spin.value()
        self._cfg["min_bbox_width_rel"]  = self._min_bbox_w_spin.value()
        self._cfg["track_grace_period_sec"]     = self._grace_spin.value()
        self._cfg["track_reid_max_distance_px"] = self._reid_dist_spin.value()
        ConfigManager().save(self._cfg)
