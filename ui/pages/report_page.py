"""Report Page — สรุป PASS/FAIL วันนี้ / สัปดาห์นี้ / เดือนนี้ (Point & Call mode)"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy,
)
from PyQt5.QtCore  import Qt, pyqtSlot
from PyQt5.QtGui   import QColor, QFont

from database.db_manager import DBManager


# ── small stat card ──────────────────────────────────────────────────────────

class _StatCard(QFrame):
    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumSize(160, 110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(4)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet("color:#6A8AAA; font-size:12px;")
        self._lbl.setAlignment(Qt.AlignCenter)

        self._val = QLabel("—")
        self._val.setAlignment(Qt.AlignCenter)
        font = QFont(); font.setPointSize(30); font.setBold(True)
        self._val.setFont(font)
        self._val.setStyleSheet(f"color:{color};")

        vbox.addWidget(self._lbl)
        vbox.addWidget(self._val)

    def set_value(self, v: int):
        self._val.setText(str(v))


# ── main page ─────────────────────────────────────────────────────────────────

class ReportPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._db  = DBManager(cfg)
        self._db.init()
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── title + controls ──────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("📊  Report"); title.setObjectName("PageTitle")
        hdr.addWidget(title)
        hdr.addStretch()

        self._period_combo = QComboBox()
        self._period_combo.addItems(["วันนี้", "7 วันล่าสุด", "เดือนนี้", "ทั้งหมด"])
        self._period_combo.currentIndexChanged.connect(self.refresh)
        hdr.addWidget(QLabel("ช่วงเวลา:"))
        hdr.addWidget(self._period_combo)

        btn = QPushButton("⟳  รีเฟรช")
        btn.clicked.connect(self.refresh)
        hdr.addWidget(btn)
        root.addLayout(hdr)

        # ── big stat cards ────────────────────────────────────────────────────
        card_row = QHBoxLayout(); card_row.setSpacing(16)
        self._card_pass  = _StatCard("✅  PASS",  "#00C853")
        self._card_fail  = _StatCard("❌  FAIL",  "#FF1744")
        self._card_intr  = _StatCard("⚠️  INTRUSION", "#FF9800")
        self._card_total = _StatCard("👤  รวมทั้งหมด", "#5A8ABF")
        for c in (self._card_pass, self._card_fail, self._card_intr, self._card_total):
            card_row.addWidget(c)
        root.addLayout(card_row)

        # ── rate bar ──────────────────────────────────────────────────────────
        rate_frame = QFrame(); rate_frame.setObjectName("Card")
        rate_layout = QHBoxLayout(rate_frame)
        rate_layout.setContentsMargins(20, 12, 20, 12)
        self._rate_lbl = QLabel("อัตรา PASS: —")
        self._rate_lbl.setStyleSheet("color:#A0C8F0; font-size:14px;")
        self._rate_lbl.setAlignment(Qt.AlignCenter)
        rate_layout.addWidget(self._rate_lbl)
        root.addWidget(rate_frame)

        # ── hourly / daily breakdown table ────────────────────────────────────
        breakdown_lbl = QLabel("รายละเอียด")
        breakdown_lbl.setStyleSheet("color:#6A8AAA; font-size:12px; font-weight:bold;")
        root.addWidget(breakdown_lbl)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ช่วงเวลา", "PASS", "FAIL", "INTRUSION"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in (1, 2, 3):
            self._table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        root.addWidget(self._table, stretch=1)

        self._footer = QLabel("")
        self._footer.setStyleSheet("color:#3A4A6A; font-size:10px;")
        root.addWidget(self._footer)

    # ── data ──────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def refresh(self):
        idx_map = {0: "today", 1: "week", 2: "month", 3: "all"}
        period  = idx_map.get(self._period_combo.currentIndex(), "today")
        data    = self._db.fetch_report(period)

        self._card_pass.set_value(data["pass"])
        self._card_fail.set_value(data["fail"])
        self._card_intr.set_value(data["intrusion"])
        self._card_total.set_value(data["total"])

        total = data["total"]
        if total > 0:
            pct = data["pass"] / total * 100
            color = "#00C853" if pct >= 80 else ("#FF9800" if pct >= 50 else "#FF1744")
            self._rate_lbl.setText(
                f'อัตรา PASS: <span style="color:{color}; font-weight:bold;">'
                f'{pct:.1f}%</span>  '
                f'({data["pass"]} PASS / {data["fail"]} FAIL / {total} รวม)'
            )
            self._rate_lbl.setTextFormat(Qt.RichText)
        else:
            self._rate_lbl.setText("อัตรา PASS: ไม่มีข้อมูล")

        # build breakdown table from hourly (today) or breakdown
        self._table.setRowCount(0)
        if period == "today" and data["hourly"]:
            for row_d in data["hourly"]:
                self._add_table_row(
                    row_d.get("hour", ""),
                    row_d.get("pass_cnt", 0),
                    row_d.get("fail_cnt", 0),
                    row_d.get("intr_cnt", 0),
                )
        else:
            # group breakdown by period key
            grouped: dict[str, dict] = {}
            for r in data["breakdown"]:
                p_key  = r.get("period", "")
                result = r.get("result", "")
                cnt    = r.get("cnt", 0)
                if p_key not in grouped:
                    grouped[p_key] = {"PASS": 0, "FAIL": 0, "INTRUSION": 0}
                grouped[p_key][result] = grouped[p_key].get(result, 0) + cnt
            for p_key in sorted(grouped.keys()):
                g = grouped[p_key]
                self._add_table_row(p_key, g["PASS"], g["FAIL"], g["INTRUSION"])

        from datetime import datetime
        self._footer.setText(
            f"อัปเดตล่าสุด: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}  |  "
            f"ฐานข้อมูล: {self._db._db_path}"
        )

    def _add_table_row(self, period: str, pass_cnt: int, fail_cnt: int, intr_cnt: int):
        row = self._table.rowCount()
        self._table.insertRow(row)
        for col, (text, color) in enumerate([
            (period,         "#A0C8F0"),
            (str(pass_cnt),  "#00C853"),
            (str(fail_cnt),  "#FF1744"),
            (str(intr_cnt),  "#FF9800"),
        ]):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(QColor(color))
            self._table.setItem(row, col, item)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
