"""History page — crossing + zone intrusion events, unified view."""
from __future__ import annotations
import csv, os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QLineEdit, QComboBox, QMessageBox, QFileDialog, QFrame,
    QTabWidget,
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
        self._result_combo.addItems(["All", "PASS", "FAIL", "INTRUSION"])
        self._result_combo.currentIndexChanged.connect(self._filter)

        for w in (self._search, self._result_combo,
                  self._make_btn("↻ Refresh", self.refresh),
                  self._make_btn("⬇ Export CSV", self._export),
                  self._make_btn("✕ Delete", self._delete, "DangerButton")):
            top.addWidget(w)
        root.addLayout(top)

        # tabs: DB events | CSV zone events
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("QTabBar::tab { min-width: 140px; padding: 6px; }")

        # --- DB tab ---
        db_tab = QWidget()
        db_layout = QVBoxLayout(db_tab)
        db_layout.setContentsMargins(0, 8, 0, 0)
        splitter = QSplitter(Qt.Horizontal)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["ID","DateTime","Track","Result","Mode","Image"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
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
        db_layout.addWidget(splitter, stretch=1)

        self._count_lbl = QLabel("0 records")
        self._count_lbl.setStyleSheet("color:#5A6A8A; font-size:11px;")
        db_layout.addWidget(self._count_lbl)
        self._tabs.addTab(db_tab, "📊  All Events (DB)")

        # --- CSV zone events tab ---
        csv_tab = QWidget()
        csv_layout = QVBoxLayout(csv_tab)
        csv_layout.setContentsMargins(0, 8, 0, 0)

        csv_hdr = QHBoxLayout()
        self._csv_refresh_btn = QPushButton("↻ Reload CSV")
        self._csv_refresh_btn.clicked.connect(self._load_csv_events)
        csv_hdr.addWidget(QLabel("Zone events CSV (offline fallback)"))
        csv_hdr.addStretch()
        csv_hdr.addWidget(self._csv_refresh_btn)
        csv_layout.addLayout(csv_hdr)

        self._csv_table = QTableWidget(0, 5)
        self._csv_table.setHorizontalHeaderLabels(["DateTime","Track","Zone","Result","Image"])
        self._csv_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._csv_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._csv_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._csv_table.itemSelectionChanged.connect(self._on_csv_select)
        csv_layout.addWidget(self._csv_table, stretch=1)
        self._tabs.addTab(csv_tab, "📁  Zone Events (CSV)")

        root.addWidget(self._tabs, stretch=1)

    def _make_btn(self, text, slot, obj=""):
        b = QPushButton(text)
        if obj: b.setObjectName(obj)
        b.clicked.connect(slot)
        return b

    def refresh(self):
        self._rows = self._db.fetch_history(500)
        self._populate(self._rows)
        self._load_csv_events()

    def _populate(self, rows):
        self._table.setRowCount(0)
        for r in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            result = r.get("result", "")
            if result == "PASS":
                color = QColor("#00C853")
            elif result == "FAIL":
                color = QColor("#FF1744")
            else:                            # INTRUSION or other
                color = QColor("#FF9800")
            for col, key in enumerate(["id","ts","track_id","result","mode","image_path"]):
                item = QTableWidgetItem(str(r.get(key, "")))
                item.setTextAlignment(Qt.AlignCenter)
                if key == "result":
                    item.setForeground(color)
                self._table.setItem(row, col, item)
        self._count_lbl.setText(f"{len(rows)} records")

    def _load_csv_events(self):
        self._csv_table.setRowCount(0)
        csv_path = os.path.join(
            self._cfg.get("capture_dir", "captures"), "zone_events.csv"
        )
        if not os.path.exists(csv_path):
            return
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            for r in reversed(rows):
                row = self._csv_table.rowCount()
                self._csv_table.insertRow(row)
                for col, key in enumerate(["ts","track_id","zone_name","result","image_path"]):
                    item = QTableWidgetItem(str(r.get(key, "")))
                    item.setTextAlignment(Qt.AlignCenter)
                    if key == "result":
                        item.setForeground(QColor("#FF9800"))
                    self._csv_table.setItem(row, col, item)
        except Exception as e:
            print(f"[History] CSV load error: {e}")

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

    @pyqtSlot()
    def _on_csv_select(self):
        row = self._csv_table.currentRow()
        if row < 0: return
        item = self._csv_table.item(row, 4)   # image_path column
        if not item: return
        path = item.text()
        if path and os.path.exists(path):
            self._tabs.setCurrentIndex(0)     # switch to DB tab for the image panel
            pix = QPixmap(path).scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._img_lbl.setPixmap(pix)
            self._img_info.setText(os.path.basename(path))

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
