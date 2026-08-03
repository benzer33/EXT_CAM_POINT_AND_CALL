"""
RTSPScanner — scan LAN subnet for RTSP cameras.

Probes port 554 across the current subnet, then tries a list of common
URL patterns for each live host.  For each successful RTSP URL it grabs
one preview frame and emits a result signal.

QThread usage:
    scanner = RTSPScanner(credentials=[("admin","REDACTED_CAMERA_PASSWORD"),("admin","REDACTED_CAMERA_PASSWORD")])
    scanner.camera_found.connect(my_slot)   # slot(ip, url, QImage)
    scanner.progress.connect(prog_slot)     # slot(current, total, ip)
    scanner.finished_scan.connect(done_slot)
    scanner.start()
    # scanner.stop() to cancel early
"""
from __future__ import annotations

import socket
import threading
import time
from urllib.parse import quote

import cv2
import numpy as np
from PyQt5.QtCore  import QThread, pyqtSignal
from PyQt5.QtGui   import QImage


# ── RTSP URL templates ────────────────────────────────────────────────────────
# {user}, {pwd}, {ip} are substituted at runtime.
# Password is URL-encoded automatically.
_URL_TEMPLATES: list[str] = [
    # Hikvision / ONVIF channel style
    "rtsp://{user}:{pwd}@{ip}:554/Streaming/Channels/101",
    "rtsp://{user}:{pwd}@{ip}:554/Streaming/Channels/102",
    "rtsp://{user}:{pwd}@{ip}:554/Streaming/Channels/201",
    # Dahua / generic
    "rtsp://{user}:{pwd}@{ip}:554/cam/realmonitor?channel=1&subtype=0",
    "rtsp://{user}:{pwd}@{ip}:554/cam/realmonitor?channel=1&subtype=1",
    # Common generic paths
    "rtsp://{user}:{pwd}@{ip}:554/stream1",
    "rtsp://{user}:{pwd}@{ip}:554/stream2",
    "rtsp://{user}:{pwd}@{ip}:554/h264",
    "rtsp://{user}:{pwd}@{ip}:554/live",
    "rtsp://{user}:{pwd}@{ip}:554/video1",
    "rtsp://{user}:{pwd}@{ip}:554/live/ch00_0",
    "rtsp://{user}:{pwd}@{ip}:554/live/ch0",
    "rtsp://{user}:{pwd}@{ip}:554/",
    # No-auth fallback
    "rtsp://{ip}:554/stream1",
    "rtsp://{ip}:554/h264",
]

PORT_TIMEOUT   = 0.8    # seconds to wait for TCP connect on port 554
RTSP_TIMEOUT   = 5.0    # seconds total budget per RTSP URL attempt
SCAN_WORKERS   = 24     # parallel port-probe threads
FRAME_WORKERS  = 4      # parallel frame-grab threads (heavier — keep low)


def _get_local_subnet() -> str:
    """Return the /24 subnet prefix of the default interface, e.g. '192.168.1.'"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        parts = ip.split(".")
        return ".".join(parts[:3]) + "."
    except Exception:
        return "192.168.1."


def _probe_port(ip: str, port: int = 554, timeout: float = PORT_TIMEOUT) -> bool:
    """Return True if TCP port is open."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def _grab_frame(url: str, timeout: float = RTSP_TIMEOUT) -> np.ndarray | None:
    """Try to open RTSP URL and grab one frame within `timeout` seconds.

    Uses a background thread with a hard-kill timer so cv2.VideoCapture()
    itself cannot block indefinitely even before timeout properties apply.
    """
    result: list[np.ndarray | None] = [None]
    done_event = threading.Event()

    def _worker():
        try:
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(timeout * 1000))
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(timeout * 1000))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            deadline = time.time() + timeout
            while time.time() < deadline and not done_event.is_set():
                ret, f = cap.read()
                if ret and f is not None:
                    result[0] = f
                    break
            cap.release()
        except Exception:
            pass
        finally:
            done_event.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    done_event.wait(timeout=timeout + 0.5)   # +0.5s grace for cap.release()
    return result[0]


def _frame_to_qimage(frame: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()


def _build_urls(ip: str, credentials: list[tuple[str, str]]) -> list[str]:
    """Expand all URL templates for given IP and credential pairs."""
    urls: list[str] = []
    for user, pwd in credentials:
        enc_pwd = quote(pwd, safe="")
        for tpl in _URL_TEMPLATES:
            urls.append(tpl.format(user=quote(user, safe=""), pwd=enc_pwd, ip=ip))
    return urls


class CameraResult:
    """Holds one discovered camera."""
    def __init__(self, ip: str, url: str, frame: np.ndarray):
        self.ip      = ip
        self.url     = url
        self.frame   = frame
        self.preview = _frame_to_qimage(frame)

    def __repr__(self):
        return f"<CameraResult ip={self.ip} url={self.url}>"


class RTSPScanner(QThread):
    """
    Scan LAN subnet for RTSP cameras.

    Signals:
        camera_found(ip, url, QImage) — emitted for each working camera
        progress(current, total, status_text) — scan progress
        finished_scan(count) — scan complete, count = cameras found
    """
    camera_found  = pyqtSignal(str, str, QImage)   # ip, url, preview
    progress      = pyqtSignal(int, int, str)       # current, total, label
    finished_scan = pyqtSignal(int)                 # total found

    def __init__(
        self,
        credentials: list[tuple[str, str]] | None = None,
        subnet: str | None = None,
        explicit_ips: list[str] | None = None,   # scan these IPs only
        parent=None,
    ):
        super().__init__(parent)
        self._credentials = credentials or [
            ("admin", "REDACTED_CAMERA_PASSWORD"),
            ("admin", "REDACTED_CAMERA_PASSWORD"),
            ("admin", "admin"),
            ("admin", "12345"),
            ("admin", ""),
        ]
        self._subnet       = subnet
        self._explicit_ips = explicit_ips or []   # if set, skip subnet scan
        self._stop  = False
        self._found = 0

    def stop(self):
        self._stop = True

    # ── internal helpers ──────────────────────────────────────────────────────

    def _scan_port(self, ip: str) -> bool:
        return _probe_port(ip)

    def _try_camera(self, ip: str) -> CameraResult | None:
        """Try all URL patterns for ip, return first that yields a frame."""
        urls = _build_urls(ip, self._credentials)
        for url in urls:
            if self._stop:
                return None
            frame = _grab_frame(url)
            if frame is not None:
                return CameraResult(ip, url, frame)
        return None

    # ── QThread entry ─────────────────────────────────────────────────────────

    def run(self):
        # If explicit IPs were given, skip subnet scan entirely
        if self._explicit_ips:
            self._run_rtsp_phase(self._explicit_ips)
            self.finished_scan.emit(self._found)
            return

        subnet = self._subnet or _get_local_subnet()
        hosts  = [f"{subnet}{i}" for i in range(1, 255)]
        total  = len(hosts)

        # ── Phase 1: port probe (fast, parallel) ──────────────────────────────
        live_hosts: list[str] = []
        lock = threading.Lock()
        done = [0]

        def probe(ip: str):
            if self._stop:
                return
            with lock:
                done[0] += 1
                n = done[0]
            self.progress.emit(n, total, f"Scanning {ip}…")
            if _probe_port(ip):
                with lock:
                    live_hosts.append(ip)

        threads = []
        sem = threading.Semaphore(SCAN_WORKERS)

        def worker(ip):
            with sem:
                probe(ip)

        for h in hosts:
            if self._stop:
                break
            t = threading.Thread(target=worker, args=(h,), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        if self._stop:
            self.finished_scan.emit(self._found)
            return

        self._run_rtsp_phase(live_hosts)
        self.finished_scan.emit(self._found)

    def _run_rtsp_phase(self, hosts: list[str]):
        """Phase 2: attempt RTSP connection + frame grab for each host."""
        lock  = threading.Lock()
        done2 = [0]
        total2 = len(hosts)
        sem2   = threading.Semaphore(FRAME_WORKERS)

        def grab_worker(ip: str):
            if self._stop:
                return
            result = self._try_camera(ip)
            with lock:
                done2[0] += 1
                nd = done2[0]
            self.progress.emit(nd, total2, f"Connecting {ip}…")
            if result:
                with lock:
                    self._found += 1
                self.camera_found.emit(result.ip, result.url, result.preview)

        threads2 = []
        for h in hosts:
            if self._stop:
                break
            def _w(ip=h):
                with sem2:
                    grab_worker(ip)
            t = threading.Thread(target=_w, daemon=True)
            t.start()
            threads2.append(t)

        for t in threads2:
            t.join()
