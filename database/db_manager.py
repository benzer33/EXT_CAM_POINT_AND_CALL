"""
DBManager — MSSQL persistence for crossing events.
"""
from __future__ import annotations
import threading
from datetime import datetime


class DBManager:
    def __init__(self, mssql_cfg: dict):
        self._cfg = mssql_cfg
        self._ok  = False

    def _conn_str(self) -> str:
        c = self._cfg
        return (
            f"DRIVER={{{c.get('driver', 'ODBC Driver 17 for SQL Server')}}};"
            f"SERVER={c.get('server', '')};"
            f"DATABASE={c.get('database', '')};"
            f"UID={c.get('username', '')};"
            f"PWD={c.get('password', '')};"
            "TrustServerCertificate=yes;"
            "Connection Timeout=5;"
        )

    def init(self) -> bool:
        try:
            import pyodbc
            conn = pyodbc.connect(self._conn_str())
            cur  = conn.cursor()
            cur.execute("""
                IF NOT EXISTS (
                    SELECT * FROM sysobjects WHERE name='crossing_events' AND xtype='U'
                )
                CREATE TABLE crossing_events (
                    id         INT IDENTITY PRIMARY KEY,
                    ts         DATETIME2 DEFAULT GETDATE(),
                    track_id   INT,
                    result     NVARCHAR(10),
                    mode       NVARCHAR(20),
                    image_path NVARCHAR(500)
                )
            """)
            conn.commit()
            conn.close()
            self._ok = True
            print(f"[DB] เชื่อมต่อสำเร็จ → {self._cfg.get('server')}/{self._cfg.get('database')}")
            return True
        except Exception as e:
            print(f"[DB] init ไม่ได้: {e}")
            return False

    def log_crossing(self, track_id: int, result: str, mode: str, image_path: str = ""):
        """Insert a crossing record in a background thread (non-blocking)."""
        def _insert():
            try:
                import pyodbc
                conn = pyodbc.connect(self._conn_str())
                conn.cursor().execute(
                    "INSERT INTO crossing_events (track_id, result, mode, image_path) "
                    "VALUES (?, ?, ?, ?)",
                    track_id, result, mode, image_path,
                )
                conn.commit()
                conn.close()
                print(f"[DB] บันทึกแล้ว → track={track_id}  {result}  ({mode})")
            except Exception as e:
                print(f"[DB] log ไม่ได้: {e}")
        threading.Thread(target=_insert, daemon=True).start()

    def fetch_history(self, limit: int = 500) -> list[dict]:
        try:
            import pyodbc
            conn = pyodbc.connect(self._conn_str())
            cur  = conn.cursor()
            cur.execute(
                f"SELECT TOP {limit} id, ts, track_id, result, mode, image_path "
                "FROM crossing_events ORDER BY id DESC"
            )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            print(f"[DB] fetch ไม่ได้: {e}")
            return []

    def delete_record(self, record_id: int):
        try:
            import pyodbc
            conn = pyodbc.connect(self._conn_str())
            conn.cursor().execute("DELETE FROM crossing_events WHERE id=?", record_id)
            conn.commit()
            conn.close()
            print(f"[DB] ลบ record id={record_id} แล้ว")
        except Exception as e:
            print(f"[DB] delete ไม่ได้: {e}")
