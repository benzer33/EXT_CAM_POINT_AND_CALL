"""
GestureClassifier — exact detection logic copied from original prototype.
DO NOT modify this logic without explicit user request.
"""
from __future__ import annotations

# ── COCO keypoint indices ─────────────────────────────────────────────────────
# After horizontal flip:
#   sL (body-left  shoulder) → RIGHT side of screen (larger x)
#   sR (body-right shoulder) → LEFT  side of screen (smaller x)
KP_NOSE       = 0
KP_SHOULDER_L = 5
KP_SHOULDER_R = 6
KP_ELBOW_L    = 7
KP_ELBOW_R    = 8
KP_WRIST_L    = 9
KP_WRIST_R    = 10
KP_HIP_L      = 11
KP_HIP_R      = 12

# ── Gesture thresholds (proportional to body size) ────────────────────────────
POINT_SIDE_RATIO        = 0.05   # kept for LOOSE mode reference / debug
POINT_HEIGHT_RATIO      = 0.40   # active zone: wrist y < shoulder_cy + body_height × this
STRAIGHT_RATIO          = 0.01   # wrist must be above torso_mid for STRAIGHT height check
STRAIGHT_SHOULDER_RATIO = 0.10   # STRICT STRAIGHT zone: |wrist_x − own_shoulder_x| < bw × this
                                  # also serves as LEFT/RIGHT threshold in STRICT mode
CENTER_RATIO            = 0.45   # kept for LOOSE mode (unused in STRICT)
HANDSUP_LEVELS          = ("waist", "chest", "shoulder")  # ระดับเกณฑ์ที่รองรับสำหรับโหมด HANDSUP


def get_kp(keypoints, idx):
    """Return (x, y, conf) or None when conf < 0.3."""
    if keypoints is None or idx >= len(keypoints):
        return None
    kp = keypoints[idx]
    x, y, conf = float(kp[0]), float(kp[1]), float(kp[2])
    return (x, y, conf) if conf >= 0.3 else None


def is_face_visible(keypoints, conf_threshold: float = 0.6) -> bool:
    """
    เช็คว่าเห็นหน้าคนไหม โดยดูจาก nose keypoint (COCO index 0)
    confidence ต่ำ = โมเดลมองไม่เห็นใบหน้า (มักเกิดตอนคนหันหลังให้กล้อง)
    """
    if keypoints is None or KP_NOSE >= len(keypoints):
        return False
    kp = keypoints[KP_NOSE]
    conf = float(kp[2])
    return conf >= conf_threshold   # ← ใช้ threshold ที่รับเข้ามาจริง ไม่พึ่ง get_kp()


def classify_pose_gesture(keypoints, mode: str = "STRICT", handsup_level: str = "waist"):
    """
    Classify pointing gesture from COCO pose keypoints.

    mode = "STRICT"   wrist must reach height threshold; correct order R→L→S required.
    mode = "LOOSE"    any order; no height limit; only LEFT/RIGHT/STRAIGHT checked.
    mode = "HANDSUP"  ตรวจว่ายกมือขึ้นสูงกว่าเกณฑ์ที่กำหนดอย่างน้อย 1 ข้าง
                      PASS = มือทั้งสองข้างขึ้นมาเหนือเกณฑ์ (wrist_y < threshold_y)
    handsup_level : str  ระดับเกณฑ์สำหรับโหมด HANDSUP —
                         "waist"    (เอว, ค่าเดิม)
                         "chest"    (หน้าอก, ประมาณจากกึ่งกลางไหล่-เอว)
                         "shoulder" (ไหล่, เข้มงวดสุด)

    Returns "LEFT" | "RIGHT" | "STRAIGHT" | "HANDSUP" | None
    """
    sL = get_kp(keypoints, KP_SHOULDER_L)
    sR = get_kp(keypoints, KP_SHOULDER_R)
    wL = get_kp(keypoints, KP_WRIST_L)
    wR = get_kp(keypoints, KP_WRIST_R)
    hL = get_kp(keypoints, KP_HIP_L)
    hR = get_kp(keypoints, KP_HIP_R)

    if not (sL and sR):
        return None

    body_width  = abs(sL[0] - sR[0])
    shoulder_cy = (sL[1] + sR[1]) / 2.0
    body_height = body_width * 1.5
    mid_x       = (sL[0] + sR[0]) / 2.0

    if body_width < 20:
        return None

    if hL and hR:
        hip_cy    = (hL[1] + hR[1]) / 2.0
        torso_mid = (shoulder_cy + hip_cy) / 2.0
    else:
        hip_cy    = shoulder_cy + body_height * 0.66
        torso_mid = shoulder_cy + body_height * 0.33

    # ── HANDSUP ───────────────────────────────────────────────────────────────
    # PASS เมื่อมือข้างใดข้างหนึ่งขึ้นสูงกว่าเกณฑ์ที่เลือก
    if mode == "HANDSUP":
        wL = get_kp(keypoints, KP_WRIST_L)
        wR = get_kp(keypoints, KP_WRIST_R)
        hL = get_kp(keypoints, KP_HIP_L)
        hR = get_kp(keypoints, KP_HIP_R)

        # คำนวณ hip_cy (ใช้ทั้ง waist และ chest)
        if hL and hR:
            hip_cy = (hL[1] + hR[1]) / 2.0
        elif hL:
            hip_cy = hL[1]
        elif hR:
            hip_cy = hR[1]
        else:
            hip_cy = shoulder_cy + body_height * 0.66

        # เลือก threshold_y ตาม handsup_level
        if handsup_level == "chest":
            threshold_y = (shoulder_cy + hip_cy) / 2.0   # กึ่งกลางไหล่-เอว
        elif handsup_level == "shoulder":
            threshold_y = shoulder_cy                     # ระดับไหล่ (เข้มงวดสุด)
        else:  # "waist" หรือค่าอื่นที่ไม่รู้จัก — fallback เป็นค่าเดิม
            threshold_y = hip_cy

        left_up  = wL is not None and wL[1] < threshold_y
        right_up = wR is not None and wR[1] < threshold_y

        # มือข้างใดข้างหนึ่งขึ้นเหนือเกณฑ์ = HANDSUP (PASS)
        if left_up or right_up:
            return "HANDSUP"
        return None

    # ── LOOSE ─────────────────────────────────────────────────────────────────
    if mode == "LOOSE":
        best = None
        if wR and wL:
            best = ("R", wR) if wR[1] < wL[1] else ("L", wL)
        elif wR:
            best = ("R", wR)
        elif wL:
            best = ("L", wL)

        if best is None:
            return None

        _, hw = best

        if hw[0] < sR[0]:       # left of sR  → LEFT gesture
            return "LEFT"
        if hw[0] > sL[0]:       # right of sL → RIGHT gesture
            return "RIGHT"
        if hw[1] < hip_cy:      # above hip   → STRAIGHT
            return "STRAIGHT"

        return None

    # ── STRICT ────────────────────────────────────────────────────────────────
    thresh_height   = body_height * POINT_HEIGHT_RATIO
    thresh_straight = body_width  * STRAIGHT_SHOULDER_RATIO  # ±10% of own shoulder
    thresh_up       = body_height * STRAIGHT_RATIO

    # Find the highest wrist that is inside the active zone
    candidates = []
    for name, w in [("L", wL), ("R", wR)]:
        if w and w[1] < shoulder_cy + thresh_height:
            candidates.append((name, w))

    if not candidates:
        return None

    hand_name, w = min(candidates, key=lambda p: p[1][1])

    # STRAIGHT: wrist stays near its own shoulder (±STRAIGHT_SHOULDER_RATIO)
    #   wR near sR  →  |wR.x − sR.x| < thresh_straight
    #   wL near sL  →  |wL.x − sL.x| < thresh_straight
    if hand_name == "R":
        dist_from_shoulder = abs(w[0] - sR[0])
        if dist_from_shoulder < thresh_straight:
            return "STRAIGHT"
        # LEFT:  wR moves left  past sR  (w.x < sR.x − thresh_straight)
        if w[0] < sR[0] - thresh_straight:
            return "LEFT"
        # RIGHT: wR moves right past sR  (w.x > sR.x + thresh_straight)
        if w[0] > sR[0] + thresh_straight:
            return "RIGHT"

    if hand_name == "L":
        dist_from_shoulder = abs(w[0] - sL[0])
        if dist_from_shoulder < thresh_straight:
            return "STRAIGHT"
        # RIGHT: wL moves right past sL  (w.x > sL.x + thresh_straight)
        if w[0] > sL[0] + thresh_straight:
            return "RIGHT"
        # LEFT:  wL moves left  past sL  (w.x < sL.x − thresh_straight)
        if w[0] < sL[0] - thresh_straight:
            return "LEFT"

    return None


# ── Drawing helpers (exact prototype logic) ───────────────────────────────────

import cv2  # noqa: E402 — optional import; only needed when drawing

SKELETON_PAIRS = [
    (KP_SHOULDER_L, KP_SHOULDER_R),
    (KP_SHOULDER_L, KP_ELBOW_L), (KP_ELBOW_L, KP_WRIST_L),
    (KP_SHOULDER_R, KP_ELBOW_R), (KP_ELBOW_R, KP_WRIST_R),
    (KP_SHOULDER_L, KP_HIP_L),   (KP_SHOULDER_R, KP_HIP_R),
    (KP_HIP_L,      KP_HIP_R),
]


def draw_skeleton(frame, keypoints, color=(80, 220, 80)):
    """Draw arm/torso connections and joint circles (matches prototype draw_skeleton)."""
    for a, b in SKELETON_PAIRS:
        kpa = get_kp(keypoints, a)
        kpb = get_kp(keypoints, b)
        if kpa and kpb:
            cv2.line(frame,
                     (int(kpa[0]), int(kpa[1])),
                     (int(kpb[0]), int(kpb[1])), color, 2)
    for idx in [KP_SHOULDER_L, KP_SHOULDER_R,
                KP_ELBOW_L,    KP_ELBOW_R,
                KP_WRIST_L,    KP_WRIST_R]:
        kp = get_kp(keypoints, idx)
        if kp:
            cv2.circle(frame, (int(kp[0]), int(kp[1])), 5, color, -1)


def draw_debug_kp(frame, keypoints, bbox):
    """
    Debug overlay — threshold lines, labelled keypoints, wrist metrics.
    Exact copy of prototype draw_debug_kp.  Toggle on/off via show_debug_overlay.
    """
    sL = get_kp(keypoints, KP_SHOULDER_L)
    sR = get_kp(keypoints, KP_SHOULDER_R)
    wL = get_kp(keypoints, KP_WRIST_L)
    wR = get_kp(keypoints, KP_WRIST_R)
    hL = get_kp(keypoints, KP_HIP_L)
    hR = get_kp(keypoints, KP_HIP_R)

    x1 = int(bbox[0])
    fh, fw = frame.shape[:2]

    # labelled keypoint dots
    for idx, lbl, col in [
        (KP_SHOULDER_L, "sL", (255, 100, 100)),
        (KP_SHOULDER_R, "sR", (100, 100, 255)),
        (KP_WRIST_L,    "wL", (255, 200,   0)),
        (KP_WRIST_R,    "wR", (  0, 200, 255)),
        (KP_HIP_L,      "hL", (200, 255, 100)),
        (KP_HIP_R,      "hR", (100, 255, 200)),
    ]:
        kp = get_kp(keypoints, idx)
        if kp:
            cx, cy = int(kp[0]), int(kp[1])
            cv2.circle(frame, (cx, cy), 8, col, -1)
            cv2.putText(frame, lbl, (cx + 6, cy - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)

    if not (sL and sR):
        return

    body_width  = abs(sL[0] - sR[0])
    shoulder_cy = (sL[1] + sR[1]) / 2.0
    body_height = body_width * 1.5

    thresh_straight = body_width  * STRAIGHT_SHOULDER_RATIO   # ±10% of own shoulder
    thresh_height   = body_height * POINT_HEIGHT_RATIO
    thresh_up       = body_height * STRAIGHT_RATIO

    if hL and hR:
        hip_cy    = (hL[1] + hR[1]) / 2.0
        torso_mid = (shoulder_cy + hip_cy) / 2.0
    else:
        hip_cy    = shoulder_cy + body_height * 0.66
        torso_mid = shoulder_cy + body_height * 0.33

    # torso_mid horizontal line
    cv2.line(frame, (0, int(torso_mid)), (fw, int(torso_mid)), (0, 200, 255), 1)
    cv2.putText(frame, f"torso_mid",
                (5, int(torso_mid) - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

    # active wrist zone horizontal line
    active_line = int(shoulder_cy + thresh_height)
    cv2.line(frame, (0, active_line), (fw, active_line), (255, 180, 0), 1)
    cv2.putText(frame, "active thresh (L/R/S)", (5, active_line - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 180, 0), 1)

    # ── Shoulder-anchored STRAIGHT / LEFT / RIGHT zones ───────────────────────
    # Each hand has its own ±thresh_straight zone around its shoulder:
    #
    #  Screen (after mirror flip):
    #  LEFT side ←  |  sR  |  <-- sR (body-right) is on LEFT of screen
    #                |L_R  |  ← sR − thresh  (wR goes LEFT  past this → LEFT)
    #                |R_R  |  → sR + thresh  (wR goes RIGHT past this → RIGHT)
    #                [STRAIGHT_R zone = sR ± thresh]
    #
    #  RIGHT side →  |  sL  |  <-- sL (body-left) is on RIGHT of screen
    #                |R_L  |  → sL + thresh  (wL goes RIGHT past this → RIGHT)
    #                |L_L  |  ← sL − thresh  (wL goes LEFT  past this → LEFT)
    #                [STRAIGHT_L zone = sL ± thresh]

    # Right-hand zone (around sR on left of screen)
    sR_left  = int(sR[0] - thresh_straight)   # wR crosses here → LEFT
    sR_right = int(sR[0] + thresh_straight)   # wR crosses here → RIGHT
    cv2.line(frame, (sR_left,  0), (sR_left,  fh), (200, 100, 255), 1)
    cv2.line(frame, (sR_right, 0), (sR_right, fh), (200, 100, 255), 1)
    cv2.putText(frame, "wR:L|", (sR_left  - 40, 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 100, 255), 1)
    cv2.putText(frame, "|wR:R", (sR_right +  2, 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 100, 255), 1)

    # Left-hand zone (around sL on right of screen)
    sL_left  = int(sL[0] - thresh_straight)   # wL crosses here → LEFT
    sL_right = int(sL[0] + thresh_straight)   # wL crosses here → RIGHT
    cv2.line(frame, (sL_left,  0), (sL_left,  fh), (100, 200, 255), 1)
    cv2.line(frame, (sL_right, 0), (sL_right, fh), (100, 200, 255), 1)
    cv2.putText(frame, "wL:L|", (sL_left  - 40, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 200, 255), 1)
    cv2.putText(frame, "|wL:R", (sL_right +  2, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 200, 255), 1)

    # wrist info for each active wrist
    for w, wname, own_shoulder in [(wR, "wR", sR), (wL, "wL", sL)]:
        if w and w[1] < shoulder_cy + thresh_height:
            dist = abs(w[0] - own_shoulder[0])
            in_straight = dist < thresh_straight
            info  = f"{wname}: dist_shldr={dist:.0f}(<{thresh_straight:.0f}=STRAIGHT)"
            col   = (0, 255, 0) if in_straight else (0, 80, 255)
            cv2.putText(frame, info, (x1, int(w[1]) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
