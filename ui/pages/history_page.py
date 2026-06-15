"""History page — crossing event table with image preview and export."""
from __future__ import annotations
import csv, os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QLineEdit, QComboBox, QMessageBox, QFileDialog, QFrame,
)
from PyQt5.QtCore  import Qt, pyqtSlot
from PyQt5.QtGui   import QPixmap, QColor

from database.db_manager import DBManager


class HistoryPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg  = cfg
        self._db   = DBManager(cfg.get("mssql", {}))
        self._rows: list[dict] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("History"); title.setObjectName("PageTitle")
        top.addWidget(title); top.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setFixedWidth(200)
        self._search.textChanged.connect(self._filter)

        self._result_combo = QComboBox()
        self._result_combo.addItems(["All", "PASS", "FAIL"])
        self._result_combo.currentIndexChanged.connect(self._filter)

        for w in (self._search, self._result_combo,
                  self._make_btn("↻ Refresh", self.refresh),
                  self._make_btn("⬇ Export CSV", self._export),
                  self._make_btn("✕ Delete", self._delete, "DangerButton")):
            top.addWidget(w)
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["ID","DateTime","Track","Result","Mode","Image"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_select)
        splitter.addWidget(self._table)

        img_panel = QFrame(); img_panel.setObjectName("Card"); img_panel.setFixedWidth(340)
        img_vbox  = QVBoxLayout(img_panel)
        self._img_lbl  = QLabel("No image")
        self._img_lbl.setAlignment(Qt.AlignCenter)
        self._img_lbl.setStyleSheet("color:#3A4A6A; background:#0D1B2A; border-radius:4px;")
        self._img_lbl.setMinimumHeight(240)
        self._img_info = QLabel(""); self._img_info.setAlignment(Qt.AlignCenter)
        self._img_info.setStyleSheet("color:#5A8ABF; font-size:11px;")
        img_vbox.addWidget(self._img_lbl, stretch=1); img_vbox.addWidget(self._img_info)
        splitter.addWidget(img_panel)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self._count_lbl = QLabel("0 records")
        self._count_lbl.setStyleSheet("color:#5A6A8A; font-size:11px;")
        root.addWidget(self._count_lbl)

    def _make_btn(self, text, slot, obj=""):
        b = QPushButton(text)
        if obj: b.setObjectName(obj)
        b.clicked.connect(slot)
        return b

    def refresh(self):
        self._rows = self._db.fetch_history(500)
        self._populate(self._rows)

    def _populate(self, rows):
        self._table.setRowCount(0)
        for r in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            result = r.get("result", "")
            color  = QColor("#00C853") if result == "PASS" else QColor("#FF1744")
            for col, key in enumerate(["id","ts","track_id","result","mode","image_path"]):
                item = QTableWidgetItem(str(r.get(key, "")))
                item.setTextAlignment(Qt.AlignCenter)
                if key == "result":
                    item.setForeground(color)
                self._table.setItem(row, col, item)
        self._count_lbl.setText(f"{len(rows)} records")

    def _filter(self):
        text   = self._search.text().lower()
        result = self._result_combo.currentText()
        self._populate([r for r in self._rows
                        if (result == "All" or r.get("result") == result)
                        and (not text or text in str(r).lower())])

    @pyqtSlot()
    def _on_select(self):
        row = self._table.currentRow()
        if row < 0: return
        item = self._table.item(row, 5)
        if not item: return
        path = item.text()
        if path and os.path.exists(path):
            pix = QPixmap(path).scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._img_lbl.setPixmap(pix)
            self._img_info.setText(os.path.basename(path))
        else:
            self._img_lbl.setText("No image"); self._img_lbl.setPixmap(QPixmap()); self._img_info.setText("")

    def _delete(self):
        row = self._table.currentRow()
        if row < 0: return
        id_item = self._table.item(row, 0)
        if not id_item: return
        if QMessageBox.question(self, "Delete", "Delete this record?") == QMessageBox.Yes:
            self._db.delete_record(int(id_item.text()))
            self.refresh()

    def _export(self):
        if not self._rows:
            QMessageBox.information(self, "Export", "No records to export."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "history.csv", "CSV (*.csv)")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self._rows[0].keys())
            w.writeheader(); w.writerows(self._rows)
        QMessageBox.information(self, "Export", f"Exported:\n{path}")
