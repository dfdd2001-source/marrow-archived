"""平台服务的路由回归测试（需要 fastapi + httpx，缺失时跳过）。

重点守护 P0 bug：/api/progress/clear 曾注册在 app.mount("/") 之后，
被静态文件挂载整个吞掉（405），清除进度后服务端记录会在下次同步时"复活"。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False


@unittest.skipUnless(HAVE_FASTAPI, "需要 fastapi/httpx（可由 serve_platform.sh 同款环境运行）")
class PlatformRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 数据文件指向临时目录，避免污染真实 data/（JSON 与 SQLite 都是）
        import backend.platform as mp
        cls.mp = mp
        cls.tmp = tempfile.mkdtemp(prefix="marrow-test-")
        mp.DATA_DIR = cls.tmp
        mp.DATA_LOCK  # noqa: B018  保持引用
        os.environ["MARROW_DB"] = os.path.join(cls.tmp, "test.db")
        import userstore
        userstore.init_db()
        cls.client = TestClient(mp.app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.pop("MARROW_DB", None)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True, "platform": True, "auth": True})

    def test_progress_clear_is_reachable(self):
        # P0 回归：清空必须在 mount("/") 之前可达，返回 200 而非 StaticFiles 的 405
        r = self.client.post("/api/progress/clear", json={"confirm": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True, "scope": "shared"})

    def test_progress_roundtrip_and_clear(self):
        r = self.client.post("/api/progress", json={"key": "test:case1", "done": True})
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/progress").json()
        self.assertEqual(data.get("test:case1"), 1)
        # 取消勾选
        self.client.post("/api/progress", json={"key": "test:case1", "done": False})
        self.assertNotIn("test:case1", self.client.get("/api/progress").json())

    def test_clear_removes_server_progress(self):
        # 用户视角的完整流程：打卡 → 清除 → 服务端不再有记录（旧 bug 会复活）
        self.client.post("/api/progress", json={"key": "test:case2", "done": True})
        self.client.post("/api/progress/clear", json={"confirm": True})
        self.assertEqual(self.client.get("/api/progress").json(), {})

    def test_core_detail_route(self):
        # 详情路由此前缺失，前端只能静默回退静态文件
        r = self.client.get("/api/cores/ladr-1a")
        self.assertEqual(r.status_code, 200)
        self.assertIn("topic", r.json())
        self.assertEqual(self.client.get("/api/cores/no-such-core").status_code, 404)

    def test_cores_list_shape(self):
        r = self.client.get("/api/cores")
        self.assertEqual(r.status_code, 200)
        items = r.json()
        self.assertIsInstance(items, list)
        if items:
            self.assertIn("id", items[0])
            self.assertIn("topic", items[0])

    def test_onboard_rejects_missing_pdf(self):
        r = self.client.post("/api/onboard", json={
            "pdf_path": "/nonexistent/no-such.pdf", "section_id": "x",
            "title": "t", "start": 1, "end": 2, "related": []})
        self.assertEqual(r.status_code, 400)

    # ---------- Phase 2 账号流程 ----------
    def _register_and_login(self, email="learner@test.dev", pw="secret1"):
        r = self.client.post("/api/auth/register", json={"email": email, "password": pw})
        self.assertEqual(r.status_code, 200)
        token = r.json()["token"]
        # 直接登录一次，验证凭据可用
        r = self.client.post("/api/auth/login", json={"email": email, "password": pw})
        self.assertEqual(r.status_code, 200)
        return token

    def test_auth_register_login_logout(self):
        self._register_and_login()
        # 重复注册被拒
        r = self.client.post("/api/auth/register", json={"email": "learner@test.dev", "password": "secret1"})
        self.assertEqual(r.status_code, 400)
        # 错误密码
        r = self.client.post("/api/auth/login", json={"email": "learner@test.dev", "password": "wrong!"})
        self.assertEqual(r.status_code, 401)
        # me / logout
        token = self._register_and_login("second@test.dev")
        r = self.client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.json()["email"], "second@test.dev")
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(self.client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code, 401)

    def test_progress_per_user_and_anonymous_isolation(self):
        token = self._register_and_login("p1@test.dev")
        # 匿名写共享层
        self.client.post("/api/progress", json={"key": "anon:key", "done": True})
        # 用户写自己的
        r = self.client.post("/api/progress", json={"key": "u1:key", "done": True},
                             headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.json()["scope"], "user")
        # 用户视角看不到匿名记录，反之亦然
        user_view = self.client.get("/api/progress", headers={"Authorization": f"Bearer {token}"}).json()
        anon_view = self.client.get("/api/progress").json()
        self.assertEqual(user_view, {"u1:key": 1})
        self.assertEqual(anon_view, {"anon:key": 1})
        # bulk 合并本地进度
        r = self.client.post("/api/progress/bulk", json={"keys": ["k1", "k2", "k3"]},
                             headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.json()["count"], 3)
        user_view = self.client.get("/api/progress", headers={"Authorization": f"Bearer {token}"}).json()
        self.assertIn("k3", user_view)
        # 未登录调 bulk 被拒
        self.assertEqual(self.client.post("/api/progress/bulk", json={"keys": ["x"]}).status_code, 401)
        # 清除只清自己
        self.client.post("/api/progress/clear", json={"confirm": True},
                         headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(self.client.get("/api/progress",
                                         headers={"Authorization": f"Bearer {token}"}).json(), {})
        self.assertEqual(self.client.get("/api/progress").json(), {"anon:key": 1})

    def test_attempt_recorded_for_user(self):
        token = self._register_and_login("a1@test.dev")
        r = self.client.post("/api/attempt", json={"core_id": "ladr-1a", "case_id": "ex_1", "text": "答案"},
                             headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.json()["scope"], "user")
        import userstore
        with userstore.connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM case_attempts").fetchone()[0]
        self.assertGreaterEqual(n, 1)

    def test_stats_scopes(self):
        # 登录用户：看到自己的进度与作答
        token = self._register_and_login("st@test.dev")
        self.client.post("/api/progress", json={"key": "ladr-1a:ex_1", "done": True},
                         headers={"Authorization": f"Bearer {token}"})
        self.client.post("/api/attempt", json={"core_id": "ladr-1a", "case_id": "ex_1", "text": "答"},
                         headers={"Authorization": f"Bearer {token}"})
        r = self.client.get("/api/stats", headers={"Authorization": f"Bearer {token}"})
        d = r.json()
        self.assertEqual(d["scope"], "user")
        self.assertEqual(d["totals"]["mastered"], 1)
        self.assertGreaterEqual(len(d["recent_attempts"]), 1)
        self.assertTrue(any(s["id"] == "ladr-1a" and s["mastered"] == 1 for s in d["sections"]))
        # 匿名：共享层，且与用户数据隔离
        r = self.client.get("/api/stats")
        d = r.json()
        self.assertEqual(d["scope"], "shared")
        self.assertTrue(all(s["mastered"] == 0 for s in d["sections"]))

    def test_core_versions_endpoint(self):
        import userstore
        userstore.add_core_version("ladr-test", {"topic": "t"}, "test")
        r = self.client.get("/api/cores/ladr-test/versions")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["extracted_by"], "test")


if __name__ == "__main__":
    unittest.main()
