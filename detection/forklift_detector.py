"""
ForkliftDetector — wraps a YOLOv8 detection model trained specifically to
detect forklifts. Only the "forklift" class is used (class index 0 ตาม
data.yaml ที่เทรนไว้ — ถ้าโมเดลมี class อื่นปนด้วย ให้กรองเอาแค่ index ที่ตรงกับ
"forklift" เท่านั้น).
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field


@dataclass
class ForkliftBox:
    bbox: np.ndarray   # [x1, y1, x2, y2]
    conf: float


class ForkliftDetector:
    FORKLIFT_CLASS_ID = 0   # ค่าเริ่มต้น อัพเดทจาก model.names ใน __init__

    def __init__(self, model_path: str = "models/forklift_best.pt",
                 conf: float = 0.4, device: str = "0"):
        from ultralytics import YOLO
        self._model  = YOLO(model_path)
        self._conf   = conf
        self._device = device
        # หา class id ของ "forklift" จาก model.names จริง ไม่ hardcode เดา
        for idx, name in self._model.names.items():
            if name.lower() == "forklift":
                self.FORKLIFT_CLASS_ID = idx
                break

    def detect(self, frame_raw: np.ndarray) -> list[ForkliftBox]:
        results = self._model(frame_raw, conf=self._conf, verbose=False,
                              device=self._device)[0]
        boxes_out: list[ForkliftBox] = []
        if results.boxes is None or len(results.boxes) == 0:
            return boxes_out
        boxes_xyxy = results.boxes.xyxy.cpu().numpy()
        confs      = results.boxes.conf.cpu().numpy()
        cls_ids    = results.boxes.cls.cpu().numpy().astype(int)
        mask       = cls_ids == self.FORKLIFT_CLASS_ID
        for bbox, cf in zip(boxes_xyxy[mask], confs[mask]):
            boxes_out.append(ForkliftBox(bbox=bbox, conf=float(cf)))
        return boxes_out


def bbox_overlap_ratio(person_bbox, forklift_bbox) -> float:
    """
    คำนวณสัดส่วนพื้นที่ของ person_bbox ที่ทับซ้อนกับ forklift_bbox
    (ไม่ใช่ IoU ธรรมดา เพราะ forklift bbox มักใหญ่กว่า person bbox มาก — ใช้สัดส่วน
    เทียบกับพื้นที่ person เท่านั้น ถึงจะสมเหตุสมผลสำหรับ "คนอยู่ในโฟล์คลิฟท์")

    Returns 0.0-1.0 — ค่าที่สูง = คนอยู่ในกรอบโฟล์คลิฟท์เป็นส่วนใหญ่
    """
    px1, py1, px2, py2 = person_bbox
    fx1, fy1, fx2, fy2 = forklift_bbox
    ix1, iy1 = max(px1, fx1), max(py1, fy1)
    ix2, iy2 = min(px2, fx2), min(py2, fy2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter_area  = (ix2 - ix1) * (iy2 - iy1)
    person_area = max(1.0, (px2 - px1) * (py2 - py1))
    return inter_area / person_area
