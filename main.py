"""
Point & Call Monitoring System — entry point.
torch MUST be the first import so Windows loads CUDA DLLs in the main thread.
"""
# ── torch first — prevents WinError 1114 ─────────────────────────────────────
try:
    import torch  # noqa
except OSError as _e:
    import sys, ctypes
    ctypes.windll.user32.MessageBoxW(
        0,
        f"PyTorch DLL failed to load:\n\n{_e}\n\n"
        "Reinstall with:\n"
        "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128",
        "PyTorch Error", 0x10)
    sys.exit(1)
# ─────────────────────────────────────────────────────────────────────────────

import sys, os
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore    import Qt, QTimer
from PyQt5.QtGui     import QPixmap, QFont, QColor

from config.config_manager import ConfigManager
from ui.styles             import apply_style
from ui.main_window        import MainWindow


def _make_splash(app: QApplication) -> QSplashScreen:
    pix = QPixmap(640, 300)
    pix.fill(QColor("#0D1B2A"))
    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    font = QFont("Segoe UI", 14); font.setBold(True); splash.setFont(font)
    splash.showMessage("Point & Call Monitoring System\nInitialising…",
                       Qt.AlignCenter | Qt.AlignBottom, QColor("#00BFFF"))
    return splash


def _warmup_gpu(cfg: dict, splash: QSplashScreen):
    """Create CUDA context in main thread before any QThread starts."""
    device = cfg.get("device", "cpu")
    if device == "cpu":
        return
    try:
        splash.showMessage("Initialising GPU…", Qt.AlignCenter | Qt.AlignBottom, QColor("#00BFFF"))
        QApplication.processEvents()
        if torch.cuda.is_available():
            torch.cuda.init()
            t = torch.zeros(1, device=device); del t
        splash.showMessage("GPU ready.", Qt.AlignCenter | Qt.AlignBottom, QColor("#00C853"))
        QApplication.processEvents()
    except Exception as e:
        splash.showMessage(f"GPU warning: {e}", Qt.AlignCenter | Qt.AlignBottom, QColor("#FFA726"))
        QApplication.processEvents()
        cfg["device"] = "cpu"


def main():
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    app = QApplication(sys.argv)
    app.setApplicationName("Point & Call Monitoring")
    app.setOrganizationName("FactoryTech")
    apply_style(app)

    splash = _make_splash(app)
    splash.show()
    app.processEvents()

    cfg = ConfigManager().load()
    _warmup_gpu(cfg, splash)

    window = MainWindow(cfg)
    QTimer.singleShot(1200, lambda: (splash.finish(window), window.show()))
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
