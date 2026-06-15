"""
RTSPProfileManager — persist named RTSP profiles as JSON.
"""
from __future__ import annotations
import json, os
from dataclasses import dataclass, asdict

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@dataclass
class RTSPProfile:
    name:     str
    host:     str
    port:     int    = 554
    path:     str    = ""
    username: str    = ""
    password: str    = ""

    def get_connection_url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        path = self.path.lstrip("/")
        return f"rtsp://{auth}{self.host}:{self.port}/{path}"


class RTSPProfileManager:
    def __init__(self, profiles_dir: str = PROFILES_DIR):
        self._dir = profiles_dir
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, name: str) -> str:
        return os.path.join(self._dir, f"{name}.json")

    def list_all(self) -> list[RTSPProfile]:
        out = []
        for f in os.listdir(self._dir):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(self._dir, f)) as fp:
                        out.append(RTSPProfile(**json.load(fp)))
                except Exception:
                    pass
        return sorted(out, key=lambda p: p.name)

    def save(self, profile: RTSPProfile):
        with open(self._path(profile.name), "w") as fp:
            json.dump(asdict(profile), fp, indent=2)

    def delete(self, name: str):
        p = self._path(name)
        if os.path.exists(p):
            os.remove(p)

    def get(self, name: str) -> RTSPProfile | None:
        p = self._path(name)
        if os.path.exists(p):
            with open(p) as fp:
                return RTSPProfile(**json.load(fp))
        return None
