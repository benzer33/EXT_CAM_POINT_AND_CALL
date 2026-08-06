"""
PoseDetector — wraps YOLOv8 Pose + ByteTrack.

รองรับทั้ง .pt (PyTorch) และ .engine (TensorRT) โดยไม่ต้องเปลี่ยน code

การ export โมเดลเป็น TensorRT สำหรับ Jetson (ทำครั้งเดียวบนเครื่อง Jetson เท่านั้น):
    yolo export model=yolov8n-pose.pt format=engine device=0 half=True imgsz=640

จากนั้นตั้งค่า config: yolo_model = "yolov8n-pose.engine"
ultralytics จะโหลด TensorRT engine โดยอัตโนมัติผ่าน YOLO(model_path) เหมือนกัน
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field


@dataclass
class PersonDetection:
    track_id:  int
    bbox:      np.ndarray
    keypoints: np.ndarray | None


@dataclass
class DetectionResult:
    persons: list[PersonDetection] = field(default_factory=list)
    frame_width:  int = 0
    frame_height: int = 0


class PoseDetector:
    def __init__(self, model_path: str = "yolov8n-pose.pt", conf: float = 0.5,
                 device: str = "cpu",
                 track_activation_threshold: float = 0.25,
                 lost_track_buffer: int = 60,
                 minimum_matching_threshold: float = 0.75,
                 frame_rate: int = 20):
        """
        Parameters
        ----------
        model_path : str
            path ไปยัง .pt (PyTorch) หรือ .engine (TensorRT) file
            TensorRT engine ต้อง export ไว้ล่วงหน้าบน Jetson ก่อนใช้งาน
        conf       : float  confidence threshold
        device     : str    "cpu", "cuda", "0" ฯลฯ (ไม่ใช้สำหรับ TensorRT engine)
        track_activation_threshold : float  ค่า confidence ขั้นต่ำในการสร้าง track ใหม่
        lost_track_buffer          : int    จำนวน frame ที่ ByteTrack จำ track ที่หายไป
                                            ก่อนจะลบทิ้ง (ตั้งสูงขึ้น = ทนทาน occlusion ดีขึ้น)
        minimum_matching_threshold : float  IoU threshold สำหรับจับคู่ detection กับ track
        frame_rate                 : int    FPS ของ stream (ใช้คำนวณ buffer ภายใน ByteTrack)
        """
        from ultralytics import YOLO
        import supervision as sv
        # YOLO() รองรับทั้ง .pt และ .engine (TensorRT) โดยอัตโนมัติ
        self._model   = YOLO(model_path)
        self._conf    = conf
        self._device  = device
        # เก็บ tracker params ไว้ใช้ตอน reset_tracker() ด้วย
        self._track_activation_threshold  = track_activation_threshold
        self._lost_track_buffer           = lost_track_buffer
        self._minimum_matching_threshold  = minimum_matching_threshold
        self._frame_rate                  = frame_rate
        self._tracker = sv.ByteTrack(
            track_activation_threshold=self._track_activation_threshold,
            lost_track_buffer=self._lost_track_buffer,
            minimum_matching_threshold=self._minimum_matching_threshold,
            frame_rate=self._frame_rate,
        )

    def process(self, frame_raw: np.ndarray, mirror: bool = False) -> tuple[np.ndarray, DetectionResult]:
        import cv2
        import supervision as sv

        results = self._model(frame_raw, conf=self._conf, verbose=False, device=self._device)[0]

        if mirror:
            frame_out = cv2.flip(frame_raw, 1)
        else:
            frame_out = frame_raw.copy()

        fh, fw     = frame_out.shape[:2]
        det_result = DetectionResult(frame_width=fw, frame_height=fh)

        if results.boxes is None or len(results.boxes) == 0:
            return frame_out, det_result

        boxes_xyxy = results.boxes.xyxy.cpu().numpy()
        confs      = results.boxes.conf.cpu().numpy()
        cls_ids    = results.boxes.cls.cpu().numpy().astype(int)
        mask       = cls_ids == 0

        if not mask.any():
            return frame_out, det_result

        orig_indices = np.where(mask)[0]

        if mirror:
            flipped_boxes = []
            for box in boxes_xyxy[mask]:
                x1, y1, x2, y2 = box
                flipped_boxes.append([fw - x2, y1, fw - x1, y2])
            proc_boxes = np.array(flipped_boxes)
        else:
            proc_boxes = boxes_xyxy[mask].copy()

        dets = sv.Detections(
            xyxy       = proc_boxes,
            confidence = confs[mask],
            class_id   = cls_ids[mask],
        )
        dets = self._tracker.update_with_detections(dets)

        kps_all = None
        if results.keypoints is not None:
            kps_all = results.keypoints.data.cpu().numpy()

        for i, track_id in enumerate(dets.tracker_id):
            if track_id is None:
                continue
            track_id = int(track_id)
            bbox = dets.xyxy[i]
            kps  = None
            if kps_all is not None and i < len(orig_indices):
                orig_i = orig_indices[i]
                if orig_i < len(kps_all):
                    kps = kps_all[orig_i].copy()
                    if mirror:
                        for kp in kps:
                            kp[0] = fw - kp[0]
            det_result.persons.append(PersonDetection(track_id=track_id, bbox=bbox, keypoints=kps))

        return frame_out, det_result

    def reset_tracker(self):
        import supervision as sv
        self._tracker = sv.ByteTrack(
            track_activation_threshold=self._track_activation_threshold,
            lost_track_buffer=self._lost_track_buffer,
            minimum_matching_threshold=self._minimum_matching_threshold,
            frame_rate=self._frame_rate,
        )
