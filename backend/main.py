"""[Phase-0 原型，非当前产品后端] core_versions 审核流的参考实现。

当前产品的实际后端是 backend/platform.py（静态托管 + 导入流水线 + JSON 文件存储），
前端 PWA 对接的是 platform 的 API 契约（/api/progress 为 {key, done}）。
本文件与 schema.sql、seed.py 保留的是 Phase 0 设计的 PostgreSQL 审核流原型
（user_id/status 契约、版本审核 approve/reject），供未来多用户/审核平台复用其
schema 设计与接口形状；它与前端不兼容，不要在本仓库现状下启动它对外服务。

连接串从环境变量 MARROW_DATABASE 读取（默认本机开发库）。
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg
import json
import os

app = FastAPI(title="Marrow API (Phase-0 prototype)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_DB = "host=localhost dbname=marrow_dev user=marrow password=marrow_dev"


def get_conn():
    return psycopg.connect(os.environ.get("MARROW_DATABASE", DEFAULT_DB))

# ---------- GET /api/cores ----------
@app.get("/api/cores")
def list_cores():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.topic, c.source_book, c.source_section, cv.review_status
        FROM cores c JOIN core_versions cv ON c.active_version_id = cv.id
        ORDER BY c.id
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "topic": r[1], "source": {"book": r[2], "section": r[3]}, "status": r[4]}
        for r in rows
    ]

# ---------- GET /api/cores/:id ----------
@app.get("/api/cores/{core_id}")
def get_core(core_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT cv.data FROM cores c JOIN core_versions cv ON c.active_version_id = cv.id
        WHERE c.id = %s
    """, (core_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "core not found or has no approved version")
    return row[0]

# ---------- POST /api/progress ----------
class ProgressIn(BaseModel):
    user_id: int
    core_id: str
    status: str

@app.post("/api/progress")
def update_progress(p: ProgressIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_progress (user_id, core_id, status, last_interacted_at)
        VALUES (%s,%s,%s, now())
        ON CONFLICT (user_id, core_id) DO UPDATE SET status = EXCLUDED.status, last_interacted_at = now()
    """, (p.user_id, p.core_id, p.status))
    conn.commit()
    conn.close()
    return {"ok": True}

# ---------- GET /api/progress/:user_id ----------
@app.get("/api/progress/{user_id}")
def get_progress(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT core_id, status, last_interacted_at FROM user_progress WHERE user_id=%s", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{"core_id": r[0], "status": r[1], "last_interacted_at": str(r[2])} for r in rows]

# ---------- POST /api/cases/:case_id/attempt ----------
class AttemptIn(BaseModel):
    user_id: int
    core_id: str
    submitted_answer: dict
    is_correct: bool

@app.post("/api/cases/{case_id}/attempt")
def submit_attempt(case_id: str, a: AttemptIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO case_attempts (user_id, core_id, case_id, submitted_answer, is_correct)
        VALUES (%s,%s,%s,%s,%s)
    """, (a.user_id, a.core_id, case_id, json.dumps(a.submitted_answer), a.is_correct))
    conn.commit()
    conn.close()
    return {"ok": True}

# ---------- POST /api/cores (管理端，注册新core) ----------
class CoreIn(BaseModel):
    id: str
    topic: str
    source_book: str
    source_section: str

@app.post("/api/cores")
def create_core(c: CoreIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO cores (id, topic, source_book, source_section) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (id) DO NOTHING",
        (c.id, c.topic, c.source_book, c.source_section),
    )
    conn.commit()
    conn.close()
    return {"ok": True}

import sys
sys.path.insert(0, '.')
from run_validation import check_case

# ---------- POST /api/cores/:id/versions (管理端, harness提交新版本) ----------
class VersionIn(BaseModel):
    data: dict
    extracted_by: str

@app.post("/api/cores/{core_id}/versions")
def submit_version(core_id: str, v: VersionIn):
    validation_summary = []
    for case in v.data.get("cases", []):
        status, detail = check_case(case)
        validation_summary.append({"case_id": case.get("id"), "status": status, "detail": detail})

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(version_number),0)+1 FROM core_versions WHERE core_id=%s", (core_id,))
    next_version = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO core_versions (core_id, version_number, data, extracted_by, review_status, validation_result)
        VALUES (%s,%s,%s,%s,'pending',%s) RETURNING id
    """, (core_id, next_version, json.dumps(v.data), v.extracted_by, json.dumps(validation_summary)))
    version_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return {"version_id": version_id, "version_number": next_version, "review_status": "pending", "validation_summary": validation_summary}

# ---------- GET /api/cores/:id/versions (管理端，查看所有版本及校验结果) ----------
@app.get("/api/cores/{core_id}/versions")
def list_versions(core_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, version_number, extracted_by, review_status, validation_result, created_at
        FROM core_versions WHERE core_id=%s ORDER BY version_number
    """, (core_id,))
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "version_number": r[1], "extracted_by": r[2], "review_status": r[3],
         "validation_summary": r[4], "created_at": str(r[5])}
        for r in rows
    ]

# ---------- POST /api/cores/:id/versions/:vid/approve (管理端) ----------
class ApproveIn(BaseModel):
    reviewed_by: str

@app.post("/api/cores/{core_id}/versions/{version_id}/approve")
def approve_version(core_id: str, version_id: int, a: ApproveIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE core_versions SET review_status='approved', reviewed_by=%s
        WHERE id=%s AND core_id=%s
    """, (a.reviewed_by, version_id, core_id))
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(404, "version not found")
    cur.execute("UPDATE cores SET active_version_id=%s, updated_at=now() WHERE id=%s", (version_id, core_id))
    conn.commit()
    conn.close()
    return {"ok": True, "active_version_id": version_id}

# ---------- POST /api/cores/:id/versions/:vid/reject (管理端) ----------
class RejectIn(BaseModel):
    reviewed_by: str

@app.post("/api/cores/{core_id}/versions/{version_id}/reject")
def reject_version(core_id: str, version_id: int, r: RejectIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE core_versions SET review_status='rejected', reviewed_by=%s
        WHERE id=%s AND core_id=%s AND review_status='pending'
    """, (r.reviewed_by, version_id, core_id))
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(404, "version not found or not pending")
    conn.commit()
    conn.close()
    return {"ok": True}
