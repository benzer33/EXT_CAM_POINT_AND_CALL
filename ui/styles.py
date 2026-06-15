"""Dark industrial QSS stylesheet."""
from PyQt5.QtWidgets import QApplication

DARK_STYLE = """
QMainWindow, QWidget { background-color: #0A1628; color: #C8D8F0; font-family: 'Segoe UI'; font-size: 13px; }

/* Sidebar */
QWidget#Sidebar { background-color: #071020; min-width: 200px; max-width: 200px; }
QLabel#SidebarTitle { color: #00BFFF; font-size: 15px; font-weight: bold; padding: 18px 12px 2px 12px; }
QLabel#SidebarSubtitle { color: #2A5A8A; font-size: 10px; padding: 0 12px 12px 12px; }

QPushButton#NavButton {
    background: transparent; color: #6A8ABF; border: none;
    text-align: left; padding: 10px 16px; font-size: 13px;
}
QPushButton#NavButton:hover { background: #0D1F3A; color: #C8D8F0; }
QPushButton#NavButton[active="true"] { background: #0D2A4A; color: #00BFFF; border-left: 3px solid #00BFFF; }

/* Content */
QStackedWidget#ContentStack { background: #0A1628; }
QLabel#PageTitle { color: #00BFFF; font-size: 20px; font-weight: bold; padding-bottom: 4px; }

/* Cards */
QFrame#Card { background: #0D1F3A; border-radius: 6px; border: 1px solid #1A3A6A; }

/* Stat boxes */
QLabel#StatValue     { color: #C8D8F0; font-size: 28px; font-weight: bold; }
QLabel#StatValuePass { color: #00C853; font-size: 28px; font-weight: bold; }
QLabel#StatValueFail { color: #FF1744; font-size: 28px; font-weight: bold; }
QLabel#StatLabel     { color: #5A8ABF; font-size: 11px; }

/* Buttons */
QPushButton {
    background: #0D2A4A; color: #C8D8F0; border: 1px solid #1A4A8A;
    border-radius: 4px; padding: 7px 18px; font-size: 13px;
}
QPushButton:hover   { background: #1A3A6A; }
QPushButton:pressed { background: #0A2040; }
QPushButton:disabled { color: #3A4A6A; border-color: #1A2A4A; }

QPushButton#StartButton  { background: #004D20; color: #00C853; border-color: #00C853; font-size: 15px; font-weight: bold; padding: 10px; }
QPushButton#StartButton:hover { background: #006030; }
QPushButton#StopButton   { background: #4D0010; color: #FF1744; border-color: #FF1744; font-size: 15px; font-weight: bold; padding: 10px; }
QPushButton#StopButton:hover  { background: #600020; }
QPushButton#SuccessButton { background: #004D20; color: #00C853; border-color: #00C853; }
QPushButton#SuccessButton:hover { background: #006030; }
QPushButton#DangerButton  { background: #4D0010; color: #FF5252; border-color: #FF5252; }
QPushButton#DangerButton:hover { background: #600020; }

/* Inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #071828; color: #C8D8F0; border: 1px solid #1A3A6A;
    border-radius: 3px; padding: 5px 8px; font-size: 13px;
    min-height: 28px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #00BFFF; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #0D1F3A; color: #C8D8F0; selection-background-color: #1A4A8A; }

/* Spin box width fix */
QDoubleSpinBox, QSpinBox { max-width: 160px; }

/* Group boxes */
QGroupBox {
    color: #5A8ABF; font-size: 11px; font-weight: bold; letter-spacing: 1px;
    border: 1px solid #1A3A6A; border-radius: 6px; margin-top: 10px; padding-top: 10px;
}
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; left: 10px; }

/* Form label alignment */
QFormLayout QLabel { font-size: 13px; color: #8AAAD0; min-width: 200px; }

/* Tables */
QTableWidget { background: #071828; color: #C8D8F0; gridline-color: #1A2A4A; border: none; font-size: 12px; }
QTableWidget::item { padding: 5px 8px; }
QTableWidget::item:selected { background: #1A3A6A; }
QHeaderView::section { background: #0D1F3A; color: #5A8ABF; border: none; padding: 6px 8px; font-size: 11px; font-weight: bold; letter-spacing: 1px; }

/* Scrollbar */
QScrollBar:vertical { background: #071020; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #1A3A6A; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* Radio / checkbox */
QRadioButton, QCheckBox { color: #C8D8F0; font-size: 13px; spacing: 8px; }
QRadioButton::indicator, QCheckBox::indicator { width: 15px; height: 15px; }

/* Status bar */
QStatusBar { background: #071020; color: #3A6A9A; font-size: 11px; }

/* Splitter */
QSplitter::handle { background: #1A3A6A; }
"""


def apply_style(app: QApplication):
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
