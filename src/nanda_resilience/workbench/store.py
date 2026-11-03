from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, request TEXT NOT NULL,
                    result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    kind TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS event_run ON events(run_id, seq);
                CREATE TABLE IF NOT EXISTS drafts (
                    run_id TEXT PRIMARY KEY, text TEXT NOT NULL, updated REAL NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    def create(self, request: dict) -> str:
        run_id = uuid.uuid4().hex[:16]
        now = time.time()
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?,?,?,NULL,NULL,?,?)",
                       (run_id, "queued", json.dumps(request), now, now))
        return run_id

    def update(self, run_id: str, status: str, result: dict | None = None,
               error: str | None = None):
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?,result=?,error=?,updated=? WHERE id=?",
                       (status, json.dumps(result) if result is not None else None,
                        error, time.time(), run_id))
        self.emit(run_id, "status", {"status": status, "error": error})

    def emit(self, run_id: str, kind: str, data: dict):
        with self.connect() as db:
            db.execute("INSERT INTO events(run_id,kind,data,created) VALUES (?,?,?,?)",
                       (run_id, kind, json.dumps(data), time.time()))

    def get(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            draft = db.execute("SELECT text FROM drafts WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["request"] = json.loads(record["request"])
        record["result"] = json.loads(record["result"]) if record["result"] else None
        record["draft"] = draft["text"] if draft else None
        return record

    def save_draft(self, run_id: str, text: str):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO drafts VALUES (?,?,?)",
                       (run_id, text, time.time()))

    def list(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,status,request,created,updated,error FROM runs ORDER BY created DESC LIMIT 100"
            ).fetchall()
        return [{**dict(row), "request": json.loads(row["request"])} for row in rows]

    def events(self, run_id: str, after: int = 0, limit: int = 250) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
                (run_id, after, limit)).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]

    def interrupt_stale(self):
        with self.connect() as db:
            stale = db.execute("SELECT id FROM runs WHERE status IN ('running','queued')").fetchall()
        for run in stale:
            self.update(run["id"], "interrupted", error="Server stopped before this run finished.")
