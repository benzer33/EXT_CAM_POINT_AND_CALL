"""
DBManager — SQLite local persistence for crossing & intrusion events.

ทำงานได้โดยไม่ต้องการ Network ทำงานได้บน Windows และ Linux (Jetson)
ไฟล์ DB อยู่ที่ captures/events.db (กำหนดได้ผ่าน config: sqlite_path)
"""
from __future__ import annotations
import os
import sqlite3
import threading
from datetime import datetime


class DBManager:
    def __init__(self, cfg: dict):
        """
        cfg คือ full app config dict
        อ่าน cfg['sqlite_path'] หรือใช้ default ที่ captures/events.db
        """
        # รองรับทั้ง full cfg และ legacy mssql-only dict
        if "sqlite_path" in cfg:
            self._db_path = cfg["sqlite_path"]
        elif "capture_dir" in cfg:
            self._db_path = os.path.join(cfg["capture_dir"], "events.db")
        else:
            # legacy: ถ้าส่ง mssql dict มา ให้ใช้ default
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._db_path = os.path.join(base, "captures", "events.db")

        self._lock = threading.Lock()
        self._ok   = False

    # ── helpers ──────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ── public API ────────────────────────────────────────────────────────────

    def init(self) -> bool:
        try:
            with self._lock:
                conn = self._connect()
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS crossing_events (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts         TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
                        track_id   INTEGER,
                        result     TEXT,
                        mode       TEXT,
                        image_path TEXT,
                        video_path TEXT DEFAULT ''
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ts ON crossing_events(ts)"
                )
                conn.commit()
                conn.close()
            # migration: เพิ่ม video_path ให้ database เดิมที่ยังไม่มี column นี้
            try:
                conn = self._connect()
                cur = conn.execute("PRAGMA table_info(crossing_events)")
                cols = [row[1] for row in cur.fetchall()]
                if "video_path" not in cols:
                    conn.execute("ALTER TABLE crossing_events ADD COLUMN video_path TEXT DEFAULT ''")
                    conn.commit()
                conn.close()
            except Exception as e:
                print(f"[DB] Migration warning: {e}")
            self._ok = True
            print(f"[DB] SQLite พร้อม → {self._db_path}")
            return True
        except Exception as e:
            print(f"[DB] init ไม่ได้: {e}")
            return False

    def log_crossing(self, track_id: int, result: str, mode: str,
                     image_path: str = "", video_path: str = "") -> None:
        """Insert บันทึกใน background thread (non-blocking)."""
        def _insert():
            try:
                with self._lock:
                    conn = self._connect()
                    conn.execute(
                        "INSERT INTO crossing_events (track_id, result, mode, image_path, video_path) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (track_id, result, mode, image_path, video_path),
                    )
                    conn.commit()
                    conn.close()
                print(f"[DB] บันทึกแล้ว → track={track_id}  {result}  ({mode})")
            except Exception as e:
                print(f"[DB] log ไม่ได้: {e}")
        threading.Thread(target=_insert, daemon=True).start()

    def fetch_history(self, limit: int = 500) -> list[dict]:
        try:
            with self._lock:
                conn = self._connect()
                cur  = conn.execute(
                    "SELECT id, ts, track_id, result, mode, image_path, video_path "
                    "FROM crossing_events ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
            return rows
        except Exception as e:
            print(f"[DB] fetch ไม่ได้: {e}")
            return []

    def delete_record(self, record_id: int) -> None:
        try:
            with self._lock:
                conn = self._connect()
                conn.execute("DELETE FROM crossing_events WHERE id=?", (record_id,))
                conn.commit()
                conn.close()
            print(f"[DB] ลบ record id={record_id} แล้ว")
        except Exception as e:
            print(f"[DB] delete ไม่ได้: {e}")

    # ── report queries ────────────────────────────────────────────────────────

    def fetch_report(self, period: str = "today") -> dict:
        """
        คืน dict สรุปสถิติ PASS/FAIL/INTRUSION

        period:
            'today'     — วันนี้
            'week'      — 7 วันที่ผ่านมา
            'month'     — เดือนปัจจุบัน
            'all'       — ทั้งหมด
        """
        try:
            if period == "today":
                where = "date(ts) = date('now', 'localtime')"
            elif period == "week":
                where = "ts >= datetime('now', '-7 days', 'localtime')"
            elif period == "month":
                where = "strftime('%Y-%m', ts) = strftime('%Y-%m', 'now', 'localtime')"
            else:
                where = "1=1"

            with self._lock:
                conn = self._connect()

                # summary counts
                cur = conn.execute(f"""
                    SELECT result, COUNT(*) as cnt
                    FROM crossing_events
                    WHERE {where}
                    GROUP BY result
                """)
                counts = {r["result"]: r["cnt"] for r in cur.fetchall()}

                # daily breakdown (last 30 days or selected period)
                if period in ("today",):
                    breakdown_where = where
                    group_fmt = "%H"
                    group_label = "hour"
                else:
                    breakdown_where = where if period != "all" else "ts >= datetime('now', '-30 days', 'localtime')"
                    group_fmt = "%Y-%m-%d"
                    group_label = "date"

                cur2 = conn.execute(f"""
                    SELECT strftime('{group_fmt}', ts) as period,
                           result, COUNT(*) as cnt
                    FROM crossing_events
                    WHERE {breakdown_where}
                    GROUP BY period, result
                    ORDER BY period
                """)
                breakdown = [dict(r) for r in cur2.fetchall()]

                # hourly for today
                cur3 = conn.execute(f"""
                    SELECT strftime('%H:00', ts) as hour,
                           SUM(CASE WHEN result='PASS' THEN 1 ELSE 0 END) as pass_cnt,
                           SUM(CASE WHEN result='FAIL' THEN 1 ELSE 0 END) as fail_cnt,
                           SUM(CASE WHEN result='INTRUSION' THEN 1 ELSE 0 END) as intr_cnt
                    FROM crossing_events
                    WHERE {where}
                    GROUP BY hour
                    ORDER BY hour
                """)
                hourly = [dict(r) for r in cur3.fetchall()]

                conn.close()

            return {
                "period":    period,
                "pass":      counts.get("PASS",      0),
                "fail":      counts.get("FAIL",      0),
                "intrusion": counts.get("INTRUSION", 0),
                "total":     sum(counts.values()),
                "breakdown": breakdown,
                "hourly":    hourly,
                "group_label": group_label,
            }
        except Exception as e:
            print(f"[DB] fetch_report ไม่ได้: {e}")
            return {"period": period, "pass": 0, "fail": 0,
                    "intrusion": 0, "total": 0,
                    "breakdown": [], "hourly": [], "group_label": "date"}

