"""
PoseDetector — wraps YOLOv8 Pose + ByteTrack.
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
    def __init__(self, model_path: str = "yolov8n-pose.pt", conf: float = 0.5, device: str = "cpu"):
        from ultralytics import YOLO
        import supervision as sv
        self._model   = YOLO(model_path)
        self._tracker = sv.ByteTrack()
        self._conf    = conf
        self._device  = device

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
        self._tracker = sv.ByteTrack()
