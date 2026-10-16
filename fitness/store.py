import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path=None):
        self.path = str(path or os.getenv("FITNESS_DB", "data/fitness.db"))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (owner TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS programs (
              id INTEGER PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL,
              created REAL NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL,
              profile TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feedback (
              id INTEGER PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS explanations (
              owner TEXT, program_id INTEGER, workout INTEGER, exercise INTEGER, body TEXT,
              PRIMARY KEY(owner, program_id, workout, exercise));
            CREATE TABLE IF NOT EXISTS states (owner TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, owner TEXT, csrf TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS jobs (owner TEXT PRIMARY KEY, expires REAL NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def get_json(self, table, owner):
        if table not in {"profiles", "states"}:
            raise ValueError("Unknown table")
        with self.connect() as db:
            row = db.execute(f"SELECT body FROM {table} WHERE owner=?", (owner,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_json(self, table, owner, body):
        if table not in {"profiles", "states"}:
            raise ValueError("Unknown table")
        with self.connect() as db:
            db.execute(f"INSERT OR REPLACE INTO {table}(owner,body) VALUES (?,?)",
                       (owner, json.dumps(body, ensure_ascii=False)))

    def programs(self, owner):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM programs WHERE owner=? ORDER BY version DESC", (owner,)).fetchall()
        return [self.decode_program(r) for r in rows]

    @staticmethod
    def decode_program(row):
        result = dict(row)
        result.pop("owner", None)
        result["body"] = json.loads(result["body"])
        result["profile"] = json.loads(result["profile"])
        return result

    def program(self, owner, pid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM programs WHERE owner=? AND id=?", (owner, pid)).fetchone()
        if not row:
            raise ValueError("Программа не найдена")
        return self.decode_program(row)

    def save_program(self, owner, body, profile, model):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM programs WHERE owner=?", (owner,)).fetchone()[0]
            # Every later version requires confirmation, even if requested via /program.
            status = "current" if version == 1 else "draft"
            cur = db.execute("INSERT INTO programs(owner,version,created,status,body,profile,model,prompt_version) VALUES (?,?,?,?,?,?,?,?)",
                (owner, version, time.time(), status, json.dumps(body, ensure_ascii=False),
                 json.dumps(profile, ensure_ascii=False), model, "1.0"))
            pid = cur.lastrowid
        return self.program(owner, pid)

    def confirm(self, owner, pid):
        self.program(owner, pid)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM programs WHERE id=? AND owner=?", (pid, owner)).fetchone()
            if row[0] != "draft":
                raise ValueError("Подтвердить можно только предложенную версию")
            db.execute("UPDATE programs SET status='archived' WHERE owner=? AND status='current'", (owner,))
            db.execute("UPDATE programs SET status='current' WHERE owner=? AND id=?", (owner, pid))

    def feedback(self, owner):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM feedback WHERE owner=? ORDER BY id DESC LIMIT 30", (owner,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    @contextmanager
    def job(self, owner):
        with self.connect() as db:
            db.execute("DELETE FROM jobs WHERE expires < ?", (time.time(),))
            try:
                db.execute("INSERT INTO jobs VALUES (?,?)", (owner, time.time()+300))
            except sqlite3.IntegrityError:
                raise ValueError("Запрос уже выполняется. Дождитесь результата")
        try:
            yield
        finally:
            with self.connect() as db:
                db.execute("DELETE FROM jobs WHERE owner=?", (owner,))
