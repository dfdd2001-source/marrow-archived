"""多用户学习数据层（Phase 2）：SQLite 实现。

表结构对齐 backend/schema.sql 的用户侧设计（users / user_progress /
case_attempts / core_versions）。SQLite 是零安装零运维的本地实现；
规模化（多进程/多机）时按 schema.sql 平移到 PostgreSQL（JSONB→TEXT）。

安全：密码 scrypt 加盐散列（标准库 hashlib），会话为 secrets.token_hex
随机 token，随 Authorization: Bearer 传入；全部查询参数化。
"""
import hashlib
import json
import os
import secrets
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_DB = os.path.join(ROOT, "data", "marrow.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  pw_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS user_progress (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 1,
  updated_at REAL NOT NULL,
  UNIQUE (user_id, key)
);
CREATE TABLE IF NOT EXISTS case_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  core_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  text TEXT,
  is_correct INTEGER,
  attempted_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS core_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  core_id TEXT NOT NULL,
  version_number INTEGER NOT NULL,
  data TEXT NOT NULL,
  extracted_by TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'approved',
  created_at REAL NOT NULL,
  UNIQUE (core_id, version_number)
);
"""


def db_path():
    return os.environ.get("MARROW_DB", DEFAULT_DB)


def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


# ---------- 密码与账号 ----------
def _hash_pw(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"),
                            n=2 ** 14, r=8, p=1).hex()
    return f"{salt}${digest}"


def _verify_pw(password, stored):
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(_hash_pw(password, salt), stored)


def register(email, password):
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("邮箱格式不正确")
    if len(password) < 6:
        raise ValueError("密码至少 6 位")
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (email, pw_hash, created_at) VALUES (?,?,?)",
                (email, _hash_pw(password), time.time()))
        except sqlite3.IntegrityError:
            raise ValueError("该邮箱已注册")
        return cur.lastrowid


def login(email, password):
    with connect() as conn:
        row = conn.execute("SELECT id, pw_hash FROM users WHERE email = ?",
                           (email.strip().lower(),)).fetchone()
    if not row or not _verify_pw(password, row["pw_hash"]):
        return None
    return row["id"]


# ---------- 会话 ----------
def create_session(user_id):
    token = secrets.token_hex(32)
    with connect() as conn:
        conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)",
                     (token, user_id, time.time()))
    return token


def user_for_token(token):
    if not token:
        return None
    with connect() as conn:
        row = conn.execute("SELECT user_id FROM sessions WHERE token = ?", (token,)).fetchone()
    return row["user_id"] if row else None


def delete_session(token):
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# ---------- 学习数据 ----------
def get_progress(user_id):
    with connect() as conn:
        rows = conn.execute("SELECT key FROM user_progress WHERE user_id = ? AND done = 1",
                            (user_id,)).fetchall()
    return {r["key"]: 1 for r in rows}


def set_progress(user_id, key, done):
    with connect() as conn:
        if done:
            conn.execute(
                "INSERT INTO user_progress (user_id, key, done, updated_at) VALUES (?,?,1,?) "
                "ON CONFLICT (user_id, key) DO UPDATE SET done = 1, updated_at = ?",
                (user_id, key, time.time(), time.time()))
        else:
            conn.execute("DELETE FROM user_progress WHERE user_id = ? AND key = ?",
                         (user_id, key))


def clear_progress(user_id):
    with connect() as conn:
        conn.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))


def list_attempts(user_id, limit=20):
    """最近作答（新→旧），供学习档案页展示。"""
    with connect() as conn:
        rows = conn.execute(
            "SELECT core_id, case_id, text, is_correct, attempted_at FROM case_attempts "
            "WHERE user_id = ? ORDER BY attempted_at DESC LIMIT ?", (user_id, limit)).fetchall()
    return [{"core_id": r["core_id"], "case_id": r["case_id"], "text": r["text"] or "",
             "is_correct": None if r["is_correct"] is None else bool(r["is_correct"]),
             "ts": r["attempted_at"]} for r in rows]


def add_attempt(user_id, core_id, case_id, text, is_correct):
    with connect() as conn:
        conn.execute(
            "INSERT INTO case_attempts (user_id, core_id, case_id, text, is_correct, attempted_at) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, core_id, case_id, (text or "")[:2000], is_correct, time.time()))


# ---------- core 版本留痕（导入流水线每次成功入库记一版） ----------
def add_core_version(core_id, data, extracted_by, review_status="approved"):
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM core_versions WHERE core_id = ?",
            (core_id,)).fetchone()
        n = row[0]
        conn.execute(
            "INSERT INTO core_versions (core_id, version_number, data, extracted_by, review_status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (core_id, n, json.dumps(data, ensure_ascii=False), extracted_by, review_status, time.time()))
    return n


def list_versions(core_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT version_number, extracted_by, review_status, created_at "
            "FROM core_versions WHERE core_id = ? ORDER BY version_number", (core_id,)).fetchall()
    return [{"version_number": r["version_number"], "extracted_by": r["extracted_by"],
             "review_status": r["review_status"], "created_at": r["created_at"]} for r in rows]
