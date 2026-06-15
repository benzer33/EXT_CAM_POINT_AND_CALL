"""
PersonState — per-track checklist and crossing state.
Logic matches original prototype exactly.
"""
import time
from dataclasses import dataclass, field

GESTURES      = ["LEFT", "RIGHT", "STRAIGHT"]
GESTURE_ORDER = ["RIGHT", "LEFT", "STRAIGHT"]   # mandatory order for STRICT
LOG_COOLDOWN  = 10.0


@dataclass
class PersonState:
    track_id:      int
    completed:     set   = field(default_factory=set)
    gesture_start: dict  = field(default_factory=dict)
    crossed:       bool  = False
    last_side:     int   = 0
    last_log_time: float = 0.0
    next_expected: int   = 0   # index into GESTURE_ORDER (STRICT mode)
    frames_seen:   int   = 0

    def reset(self):
        self.completed.clear()
        self.gesture_start.clear()
        self.crossed       = False
        self.last_side     = 0
        self.last_log_time = 0.0
        self.next_expected = 0
        self.frames_seen   = 0

    def can_log(self, cooldown: float = LOG_COOLDOWN) -> bool:
        return (time.time() - self.last_log_time) >= cooldown

    def accept_gesture(self, gesture: str, mode: str) -> bool:
        """
        LOOSE : accept any gesture not yet completed.
        STRICT: accept only the next gesture in GESTURE_ORDER.
        """
        if gesture in self.completed:
            return False
        if mode == "LOOSE":
            return True
        # STRICT — must follow GESTURE_ORDER sequence
        if self.next_expected < len(GESTURE_ORDER):
            return gesture == GESTURE_ORDER[self.next_expected]
        return False

    def passed_for_mode(self, mode: str) -> bool:
        """
        LOOSE : LEFT + RIGHT both completed.
        STRICT: all three gestures in correct order (next_expected reached end).
        """
        if mode == "LOOSE":
            return {"LEFT", "RIGHT"}.issubset(self.completed)
        return self.next_expected >= len(GESTURE_ORDER)
