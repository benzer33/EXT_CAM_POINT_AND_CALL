"""
TeamsNotifier — send Microsoft Teams webhook notifications.
"""
from __future__ import annotations


class TeamsNotifier:
    def __init__(self, webhook_url: str = "", send_pass: bool = False, send_fail: bool = True):
        self._url       = webhook_url
        self._send_pass = send_pass
        self._send_fail = send_fail

    def notify(self, track_id: int, result: str, mode: str, image_path: str = ""):
        if not self._url:
            return
        if result == "PASS" and not self._send_pass:
            return
        if result == "FAIL" and not self._send_fail:
            return
        try:
            import requests
            requests.post(self._url, json=self._build_payload(track_id, result, mode), timeout=5)
        except Exception as e:
            print(f"[Teams] notify failed: {e}")

    def test(self) -> tuple[bool, str]:
        if not self._url:
            return False, "No webhook URL configured"
        try:
            import requests
            r = requests.post(self._url, json=self._build_payload(0, "TEST", "TEST"), timeout=5)
            return r.status_code == 200, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)

    def _build_payload(self, track_id: int, result: str, mode: str) -> dict:
        color = "00C853" if result == "PASS" else "FF1744"
        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard", "version": "1.2",
                    "body": [{"type": "TextBlock",
                               "text": f"Point & Call — {result}",
                               "size": "Large", "weight": "Bolder",
                               "color": "Good" if result == "PASS" else "Attention"},
                              {"type": "FactSet", "facts": [
                                  {"title": "Track ID", "value": str(track_id)},
                                  {"title": "Result",   "value": result},
                                  {"title": "Mode",     "value": mode},
                              ]}]
                }
            }]
        }
