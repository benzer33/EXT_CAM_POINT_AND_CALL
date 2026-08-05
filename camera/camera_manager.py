"""
CameraManager — OpenCV video source wrapper.
รองรับทั้ง Windows (DirectShow) และ Linux/Jetson (V4L2 / GStreamer NVDEC)
"""
from __future__ import annotations
import sys
import cv2
import numpy as np


def _build_gst_pipeline(rtsp_url: str, out_w: int, out_h: int, codec: str) -> str:
    """
    สร้าง GStreamer pipeline string สำหรับ RTSP → NVDEC hardware decode บน Jetson.

    ใช้ nvv4l2decoder (NVDEC) decode บน hardware ทันที จากนั้น nvvidconv resize/convert
    ในขั้นเดียวกัน ไม่ decode เต็มความละเอียดแล้ว resize ทีหลังผ่าน CPU

    Parameters
    ----------
    rtsp_url : str  URL ของ RTSP stream เช่น "rtsp://user:pass@192.168.1.1/stream1"
    out_w    : int  ความกว้างของ output frame ที่ต้องการ (px)
    out_h    : int  ความสูงของ output frame ที่ต้องการ (px)
    codec    : str  "h264" หรือ "h265" / "hevc"

    Returns
    -------
    str  GStreamer pipeline string สำหรับส่งให้ cv2.VideoCapture
    """
    codec_lower = codec.lower().replace("hevc", "h265")
    if codec_lower == "h265":
        depay  = "rtph265depay"
        parser = "h265parse"
    else:
        depay  = "rtph264depay"
        parser = "h264parse"

    return (
        f"rtspsrc location={rtsp_url} latency=100 ! "
        f"{depay} ! {parser} ! "
        f"nvv4l2decoder ! "
        f"nvvidconv output-buffers=1 interpolation-method=1 ! "
        f"video/x-raw,width={out_w},height={out_h},format=BGRx ! "
        f"videoconvert ! "
        f"video/x-raw,format=BGR ! "
        f"appsink drop=1 sync=0 max-buffers=1"
    )


class CameraManager:
    def __init__(self):
        self._cap: cv2.VideoCapture | None = None
        self._source = None

    def connect(self, source, target_w: int = 1920, target_h: int = 1080,
                codec: str = "h264") -> bool:
        """
        เปิด video source.

        Parameters
        ----------
        source   : int หรือ str  webcam index หรือ RTSP URL
        target_w : int  ความกว้าง output ที่ต้องการ (ใช้กับ GStreamer pipeline เท่านั้น)
        target_h : int  ความสูง output ที่ต้องการ (ใช้กับ GStreamer pipeline เท่านั้น)
        codec    : str  "h264" หรือ "h265" (ใช้กับ GStreamer pipeline เท่านั้น)

        Returns
        -------
        bool  True ถ้าเปิดสำเร็จ
        """
        self.disconnect()
        try:
            if str(source).isdigit():
                # ── webcam index: ใช้ logic เดิม ────────────────────────────
                src = int(source)
                if sys.platform == "win32":
                    # Windows: DirectShow ให้ latency ต่ำสุด
                    self._cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
                    if not self._cap.isOpened():
                        self._cap.release()
                        self._cap = cv2.VideoCapture(src)
                else:
                    # Linux/Jetson: ใช้ V4L2 หรือ default backend
                    self._cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
                    if not self._cap.isOpened():
                        self._cap.release()
                        self._cap = cv2.VideoCapture(src)

            elif isinstance(source, str) and source.lower().startswith("rtsp") \
                    and sys.platform != "win32":
                # ── RTSP บน Linux/Jetson: ลอง GStreamer NVDEC ก่อน ─────────
                pipeline = _build_gst_pipeline(source, target_w, target_h, codec)
                try:
                    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                    if cap.isOpened():
                        # ทดสอบอ่านเฟรมแรกจริงๆ ก่อนประกาศว่าสำเร็จ
                        ret, _ = cap.read()
                        if ret:
                            self._cap = cap
                        else:
                            cap.release()
                            raise RuntimeError("GStreamer pipeline opened but read() failed")
                    else:
                        cap.release()
                        raise RuntimeError("GStreamer pipeline did not open")
                except Exception as gst_err:
                    # fallback: ใช้ CAP_FFMPEG เหมือนเดิม ถ้า nvv4l2decoder ไม่พร้อม
                    print(f"[CameraManager] ⚠ GStreamer NVDEC ไม่สำเร็จ ({gst_err}), "
                          f"fallback → CAP_FFMPEG")
                    self._cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
                    if self._cap.isOpened():
                        self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                        self._cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
                        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            else:
                # ── RTSP บน Windows หรือ source อื่นๆ: ใช้ CAP_FFMPEG เดิม ─
                src = source
                self._cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
                if isinstance(src, str) and src.lower().startswith("rtsp"):
                    self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                    self._cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
                    self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self._cap or not self._cap.isOpened():
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

