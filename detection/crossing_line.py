"""
CrossingLine — two-point line geometry and side detection.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CrossingLine:
    p1: tuple = (0, 0)
    p2: tuple = (0, 0)
    active: bool = False

    def set_points(self, p1: tuple, p2: tuple):
        self.p1 = tuple(p1)
        self.p2 = tuple(p2)
        self.active = True

    def clear(self):
        self.active = False

    def side(self, px: float, py: float) -> int:
        x1, y1 = self.p1
        x2, y2 = self.p2
        val = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
        if val > 0:
            return 1
        elif val < 0:
            return -1
        return 0

    def to_dict(self) -> dict:
        return {"p1": list(self.p1), "p2": list(self.p2)}

    @classmethod
    def from_dict(cls, d: dict) -> "CrossingLine":
        obj = cls()
        if d and "p1" in d and "p2" in d:
            obj.set_points(tuple(d["p1"]), tuple(d["p2"]))
        return obj
