"""userstore（SQLite 多用户层）单元测试 + 平台账号端点回归。

数据库通过 MARROW_DB 环境变量指向临时文件，不触碰真实 data/marrow.db。
"""
import os
import sys
import tempfile
import platform  # noqa: F401  # 先钉住标准库，防止 backend/platform.py 在 sys.path 上遮蔽它
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import userstore  # noqa: E402


class UserstoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(prefix="marrow-ut-", suffix=".db")
        os.close(fd)
        os.environ["MARROW_DB"] = self.path
        userstore.init_db()

    def tearDown(self):
        os.unlink(self.path)
        del os.environ["MARROW_DB"]

    def test_register_login_roundtrip(self):
        uid = userstore.register("A@Example.com ", "secret1")
        self.assertIsInstance(uid, int)
        self.assertIsNotNone(userstore.login("a@example.com", "secret1"))
        self.assertIsNone(userstore.login("a@example.com", "wrong!"))

    def test_register_validation(self):
        with self.assertRaises(ValueError):
            userstore.register("not-an-email", "secret1")
        with self.assertRaises(ValueError):
            userstore.register("a@b.com", "123")
        userstore.register("a@b.com", "secret1")
        with self.assertRaises(ValueError):
            userstore.register("a@b.com", "secret2")  # 重复邮箱

    def test_session_lifecycle(self):
        uid = userstore.register("s@b.com", "secret1")
        token = userstore.create_session(uid)
        self.assertEqual(userstore.user_for_token(token), uid)
        self.assertIsNone(userstore.user_for_token("bogus"))
        self.assertIsNone(userstore.user_for_token(None))
        userstore.delete_session(token)
        self.assertIsNone(userstore.user_for_token(token))

    def test_progress_isolated_per_user(self):
        u1 = userstore.register("u1@b.com", "secret1")
        u2 = userstore.register("u2@b.com", "secret1")
        userstore.set_progress(u1, "ladr-1a:ex_1", True)
        userstore.set_progress(u1, "ladr-1a:ex_2", True)
        self.assertEqual(userstore.get_progress(u1), {"ladr-1a:ex_1": 1, "ladr-1a:ex_2": 1})
        self.assertEqual(userstore.get_progress(u2), {})
        userstore.set_progress(u1, "ladr-1a:ex_1", False)
        self.assertEqual(userstore.get_progress(u1), {"ladr-1a:ex_2": 1})
        userstore.clear_progress(u1)
        self.assertEqual(userstore.get_progress(u1), {})

    def test_attempts_recorded(self):
        uid = userstore.register("t@b.com", "secret1")
        userstore.add_attempt(uid, "ladr-1a", "ex_1", "我的作答", True)
        with userstore.connect() as conn:
            row = conn.execute("SELECT core_id, case_id, text, is_correct FROM case_attempts").fetchone()
        self.assertEqual((row["core_id"], row["case_id"], row["is_correct"]),
                         ("ladr-1a", "ex_1", 1))

    def test_list_attempts_recent_first(self):
        uid = userstore.register("l@b.com", "secret1")
        for i in range(3):
            userstore.add_attempt(uid, "ladr-1a", f"ex_{i}", f"作答{i}", i % 2 == 0)
        rows = userstore.list_attempts(uid, 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["case_id"], "ex_2")  # 新→旧
        self.assertIsInstance(rows[0]["is_correct"], bool)

    def test_core_versions_increment(self):
        userstore.add_core_version("ladr-1a", {"topic": "t"}, "marrow_onboard")
        n2 = userstore.add_core_version("ladr-1a", {"topic": "t2"}, "marrow_onboard")
        userstore.add_core_version("ladr-1b", {"topic": "u"}, "marrow_onboard")
        self.assertEqual(n2, 2)
        versions = userstore.list_versions("ladr-1a")
        self.assertEqual([v["version_number"] for v in versions], [1, 2])
        self.assertEqual(versions[0]["review_status"], "approved")


if __name__ == "__main__":
    unittest.main()
