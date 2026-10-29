"""Marrow 平台服务：把"导入任意书"变成网页操作。

- 静态托管 PWA（app/）与 API 同源
- POST /api/import/detect：对任意 PDF 做章节标题探测（启发式，返回候选清单供人工确认）
- POST /api/onboard：为选定章节启动 marrow_onboard 流水线（后台任务）
- GET  /api/jobs：任务状态与日志
- cores/index.json 自动重建：新书/新节入库后首页立即可见

安全边界：仅绑定 127.0.0.1，供本机使用；pdf_path 为本机路径（本地信任模型）。
启动：./scripts/serve_platform.sh（固定使用 /opt/anaconda3/bin/python3，fastapi 所在环境）
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP_DIR = os.path.join(ROOT, "app")
sys.path.insert(0, ROOT)
from envtools import load_env  # noqa: E402
from backend import userstore  # noqa: E402

# 流水线用的 Python 解释器：优先 MARROW_PY 环境变量，其次本机 Anaconda，最后当前解释器
_PY_CANDIDATES = [
    os.environ.get("MARROW_PY"),
    "/opt/anaconda3/bin/python3",
    sys.executable,
]
PY = next(p for p in _PY_CANDIDATES if p and os.path.exists(os.path.normpath(p)))

app = FastAPI(title="Marrow Platform")

JOBS = {}  # id -> {"status": running/done/failed, "log": str, "started": ts, "section_id": ...}
JOBS_LOCK = threading.Lock()
JOBS_MAX = 50  # 只保留最近 N 个任务记录，防止长驻进程内存无界增长


# ---------- cores 索引 ----------
def read_cores():
    """扫描 cores/ 生成索引条目（纯读取，无副作用）。"""
    items = []
    for p in sorted(glob.glob(os.path.join(ROOT, "cores", "*.json"))):
        try:
            c = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        items.append({
            "id": os.path.basename(p)[:-5],
            "topic": c.get("topic", ""),
            "source": c.get("source", {}),
        })
    items.sort(key=lambda x: (x["source"].get("book", ""), x["id"]))
    return items


def regen_index():
    """重建 app/cores/index.json（写盘）。只在任务成功后与启动时调用；
    GET /api/cores 是纯读取，不写文件。"""
    items = read_cores()
    with open(os.path.join(APP_DIR, "cores-index.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    return items


@app.get("/api/cores")
def api_cores():
    return read_cores()


@app.get("/api/books")
def api_books():
    items = read_cores()
    books = {}
    for it in items:
        b = it["source"].get("book", "未命名书籍")
        books.setdefault(b, []).append(it)
    return [{"book": k, "sections": v} for k, v in books.items()]


# ---------- PDF 章节探测 ----------
CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章\s*(\S.*)")
SECTION_RE = re.compile(r"^\s*(\d{1,2}\s*[A-Z])\s+(\S.{1,40})\s*$")


def detect_sections(pdf_path):
    txt = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True, timeout=300).stdout
    pages = txt.split("\f")
    chapters, sections = [], []
    for pno, page in enumerate(pages, start=1):
        for raw in page.splitlines():
            line = raw.strip()
            if not line or len(line) > 44:
                continue
            m = CHAPTER_RE.search(line)
            if m and not re.search(r"[，。；]", line):
                chapters.append({"chapter": int(m.group(1)), "title": m.group(2).strip(), "page": pno})
                continue
            m = SECTION_RE.match(line)
            if m:
                sections.append({
                    "key": re.sub(r"\s+", "", m.group(1)),
                    "title": m.group(2).strip(),
                    "page": pno,
                })
    # 相邻同 key 去重（页眉重复），保留首次出现
    seen, dedup = set(), []
    for s in sections:
        if s["key"] in seen:
            continue
        seen.add(s["key"])
        dedup.append(s)
    # 推断每节结束页 = 下一节起始页（章内）
    for i, s in enumerate(dedup):
        s["end_page"] = dedup[i + 1]["page"] - 1 if i + 1 < len(dedup) else None
    return {"chapters": chapters, "sections": dedup, "total_pages": len(pages)}


class DetectIn(BaseModel):
    pdf_path: str


@app.post("/api/import/detect")
def api_detect(body: DetectIn):
    if not os.path.exists(body.pdf_path):
        return JSONResponse({"error": f"文件不存在: {body.pdf_path}"}, status_code=400)
    try:
        return detect_sections(body.pdf_path)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------- onboarding 任务 ----------
class OnboardIn(BaseModel):
    pdf_path: str
    section_id: str
    title: str
    start: int
    end: int
    related: list[str] = []


def run_job(job_id, cmd, env, section_id):
    log_path = f"/tmp/marrow-job-{job_id}.log"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=ROOT)
    ok = proc.returncode == 0
    if ok:
        try:
            regen_index()
            version_path = os.path.join(ROOT, "cores", f"{section_id}.json")
            if os.path.exists(version_path):
                with open(version_path, encoding="utf-8") as f:
                    userstore.add_core_version(section_id, json.load(f), "marrow_onboard")
        except Exception as e:
            with JOBS_LOCK:
                JOBS[job_id]["log"] += f"\n[索引重建失败] {e}"
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "done" if ok else "failed"
        JOBS[job_id]["finished"] = time.time()


@app.post("/api/onboard")
def api_onboard(body: OnboardIn):
    if not os.path.exists(body.pdf_path):
        return JSONResponse({"error": "PDF 不存在"}, status_code=400)
    # 纳秒时间戳：秒级 int(time.time()) 会在同秒并发提交时碰撞
    job_id = f"job{time.time_ns()}"
    cmd = [PY, os.path.join(ROOT, "scripts", "marrow_onboard.py"),
           "--section-id", body.section_id, "--pdf", body.pdf_path,
           "--pages", f"{body.start}-{body.end}", "--section", body.title,
           "--samples", "3"]
    for r in body.related:
        cmd += ["--related", r]
    env = load_env()
    if "AGNES_API_KEY" not in env:
        return JSONResponse({"error": "缺少 AGNES_API_KEY（.env）"}, status_code=400)
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "log": "", "started": time.time(),
                        "section_id": body.section_id}
        finished = sorted((j for j in JOBS.values() if j["status"] != "running"),
                          key=lambda j: j.get("finished", 0))
        for old in finished[:max(0, len(JOBS) - JOBS_MAX)]:
            key = next(k for k, v in JOBS.items() if v is old)
            del JOBS[key]
    threading.Thread(target=run_job, args=(job_id, cmd, env, body.section_id), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs")
def api_jobs():
    with JOBS_LOCK:
        return [{"id": k, **{kk: vv for kk, vv in v.items() if kk != "log"}} for k, v in JOBS.items()]


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "任务不存在"}, status_code=404)
    try:
        job["log"] = open(f"/tmp/marrow-job-{job_id}.log", encoding="utf-8").read()[-4000:]
    except Exception:
        pass
    return job


# ---------- 学习数据：进度同步 + 习题作答记录（对应产品文档 user_progress / case_attempts） ----------
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DATA_LOCK = threading.Lock()  # progress/attempts 是读-改-写，无锁会在并发提交时互相覆盖


def _load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return default
    return default


@app.on_event("startup")
def _startup():
    try:
        regen_index()  # 确保 app/cores/index.json 与 cores/ 一致（GET 请求不再写盘）
    except Exception:
        pass
    userstore.init_db()


@app.get("/api/health")
def api_health():
    return {"ok": True, "platform": True, "auth": True}


# ---------- 账号（Phase 2）：注册/登录/会话，SQLite 存储 ----------
def _auth_user(request: Request):
    """从 Authorization: Bearer <token> 解析用户；未登录返回 None（匿名模式）。"""
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    return userstore.user_for_token(token)


class AuthIn(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
def api_auth_register(body: AuthIn):
    try:
        user_id = userstore.register(body.email, body.password)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "user_id": user_id, "token": userstore.create_session(user_id)}


@app.post("/api/auth/login")
def api_auth_login(body: AuthIn):
    user_id = userstore.login(body.email, body.password)
    if not user_id:
        return JSONResponse({"error": "邮箱或密码不正确"}, status_code=401)
    return {"ok": True, "user_id": user_id, "token": userstore.create_session(user_id)}


@app.post("/api/auth/logout")
def api_auth_logout(request: Request):
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    userstore.delete_session(token)
    return {"ok": True}


@app.get("/api/me")
def api_me(request: Request):
    user_id = _auth_user(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    with userstore.connect() as conn:
        row = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"user_id": user_id, "email": row["email"]}


@app.get("/api/progress")
def api_progress(request: Request):
    user_id = _auth_user(request)
    if user_id:
        return userstore.get_progress(user_id)
    return _load_json(os.path.join(DATA_DIR, "progress.json"), {})


class ProgressIn(BaseModel):
    key: str
    done: bool


@app.post("/api/progress")
def api_progress_post(request: Request, body: ProgressIn):
    user_id = _auth_user(request)
    if user_id:
        userstore.set_progress(user_id, body.key, body.done)
        return {"ok": True, "scope": "user"}
    path = os.path.join(DATA_DIR, "progress.json")
    with DATA_LOCK:
        data = _load_json(path, {})
        if body.done:
            data[body.key] = 1
        else:
            data.pop(body.key, None)
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"ok": True, "scope": "shared"}


class BulkProgressIn(BaseModel):
    keys: list[str]


@app.post("/api/progress/bulk")
def api_progress_bulk(request: Request, body: BulkProgressIn):
    """登录后把本地已有进度一次性并入账号（幂等）。"""
    user_id = _auth_user(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    for key in body.keys[:5000]:
        userstore.set_progress(user_id, key, True)
    return {"ok": True, "count": len(body.keys)}


class AttemptIn(BaseModel):
    core_id: str
    case_id: str
    text: str


def _norm_answer(s):
    return re.sub(r"[\s，。；、,.();()（）「」\"']", "", str(s)).lower()


@app.post("/api/attempt")
def api_attempt(request: Request, body: AttemptIn):
    # 与机器验证答案自动比对（有 candidate_answer 时）
    reference, is_correct = None, None
    core_path = os.path.join(ROOT, "cores", f"{body.core_id}.json")
    if os.path.exists(core_path):
        core = json.load(open(core_path, encoding="utf-8"))
        cases = core.get("cases", []) + core.get("cases_practice", [])
        case = next((c for c in cases if c.get("id") == body.case_id), None)
        if case and case.get("candidate_answer"):
            reference = case["candidate_answer"]
            nu, nr = _norm_answer(body.text), _norm_answer(reference)
            # 自由文本判分不可靠：只在能确认一致时给 ✓，否则中性记录（避免误判挫败感）
            is_correct = True if (nu == nr or (len(nu) >= 6 and nu in nr) or (len(nr) >= 6 and nr in nu)) else None
    user_id = _auth_user(request)
    if user_id:
        userstore.add_attempt(user_id, body.core_id, body.case_id, body.text, is_correct)
        return {"ok": True, "is_correct": is_correct, "reference": reference, "scope": "user"}
    attempts = _load_json(os.path.join(DATA_DIR, "attempts.json"), [])
    with DATA_LOCK:
        attempts.append({"ts": time.time(), "core_id": body.core_id, "case_id": body.case_id,
                         "text": body.text[:2000], "is_correct": is_correct})
        json.dump(attempts, open(os.path.join(DATA_DIR, "attempts.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    return {"ok": True, "is_correct": is_correct, "reference": reference}


class ClearIn(BaseModel):
    confirm: bool = True


@app.post("/api/progress/clear")
def api_progress_clear(request: Request, body: ClearIn):
    # 注意：必须注册在 app.mount("/") 之前——Starlette 按注册顺序匹配，
    # mount 在前会把本路由整个吞掉（曾经的 P0 bug：清除进度端点不可达，
    # 服务端记录在下次启动同步时"复活"）。
    user_id = _auth_user(request)
    if user_id:
        userstore.clear_progress(user_id)
        return {"ok": True, "scope": "user"}
    path = os.path.join(DATA_DIR, "progress.json")
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True, "scope": "shared"}


@app.get("/api/cores/{core_id}")
def api_core(core_id: str):
    """单节详情（此前缺失：前端一直 404 后静默回退静态文件，现补正式路由）。"""
    path = os.path.join(ROOT, "cores", f"{core_id}.json")
    if not os.path.exists(path):
        return JSONResponse({"error": "core not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/stats")
def api_stats(request: Request):
    """学习档案：跨节掌握进度 + 最近作答。登录用户看自己的，匿名看共享层。"""
    user_id = _auth_user(request)
    if user_id:
        progress = userstore.get_progress(user_id)
        recent = userstore.list_attempts(user_id, 20)
        scope = "user"
    else:
        progress = _load_json(os.path.join(DATA_DIR, "progress.json"), {})
        all_attempts = _load_json(os.path.join(DATA_DIR, "attempts.json"), [])
        recent = [{"core_id": a.get("core_id"), "case_id": a.get("case_id"),
                   "text": (a.get("text") or "")[:80], "is_correct": a.get("is_correct"),
                   "ts": a.get("ts")} for a in reversed(all_attempts[-20:])]
        scope = "shared"
    sections, mastered_total, exercise_total = [], 0, 0
    for it in read_cores():
        core_path = os.path.join(ROOT, "cores", f"{it['id']}.json")
        try:
            with open(core_path, encoding="utf-8") as f:
                core = json.load(f)
        except Exception:
            continue
        total = len(core.get("cases_practice", []))
        mastered = sum(1 for k in progress if k.startswith(it["id"] + ":"))
        mastered_total += mastered
        exercise_total += total
        sections.append({"id": it["id"], "topic": it["topic"], "mastered": mastered, "total": total})
    return {"scope": scope, "sections": sections, "recent_attempts": recent,
            "totals": {"mastered": mastered_total, "exercises": exercise_total}}


@app.get("/api/cores/{core_id}/versions")
def api_core_versions(core_id: str):
    return userstore.list_versions(core_id)


# ---------- 静态托管 ----------
# cores/ 直接挂载：app/cores 是指向它的符号链接，而 StaticFiles 默认不跟随
# 指向目录外的链接（目录逃逸保护），所以这里按真实目录显式挂载。
app.mount("/cores", StaticFiles(directory=os.path.join(ROOT, "cores")), name="cores")
# PWA 兜底（必须放在所有 API 路由之后）
app.mount("/", StaticFiles(directory=APP_DIR, html=True), name="app")
