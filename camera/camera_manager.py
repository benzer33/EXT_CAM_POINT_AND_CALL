"""
CameraManager — OpenCV video source wrapper.
"""
from __future__ import annotations
import cv2
import numpy as np


class CameraManager:
    def __init__(self):
        self._cap: cv2.VideoCapture | None = None
        self._source = None

    def connect(self, source) -> bool:
        self.disconnect()
        try:
            # integer or numeric string → webcam index, use DirectShow on Windows
            if str(source).isdigit():
                src = int(source)
                self._cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
                if not self._cap.isOpened():
                    # fallback: try without explicit backend
                    self._cap.release()
                    self._cap = cv2.VideoCapture(src)
            else:
                src = source
                self._cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
                # RTSP tuning: short open/read timeout, minimal buffer
                if isinstance(src, str) and src.lower().startswith("rtsp"):
                    self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                    self._cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
                    self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not self._cap.isOpened():
                self._cap = None
                return False
            self._source = source
            return True
        except Exception:
            return False

    def disconnect(self):
        if self._cap:
            self._cap.release()
            self._cap = None

    def read(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        return frame if ret else None

    def get_fps(self) -> float:
        if self._cap:
            return self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        return 30.0

    def get_resolution(self) -> tuple[int, int]:
        if self._cap:
            return (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        return (0, 0)

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
