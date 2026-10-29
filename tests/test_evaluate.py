"""评测器引用归一化的单元测试：harness/evaluate.py"""
import os
import sys
import platform  # noqa: F401  # 先钉住标准库，防止 backend/platform.py 在 sys.path 上遮蔽它
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "harness"), os.path.join(ROOT, "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from evaluate import _norm_ref  # noqa: E402


class NormRefTest(unittest.TestCase):
    def test_exercise_refs_align_across_generations(self):
        # 基线"习题3"、平台导入"习题2A.3"、盲测"习题2a3" 必须对齐到同一题号
        self.assertEqual(_norm_ref("习题3"), _norm_ref("习题2a3"))
        self.assertEqual(_norm_ref("习题3"), _norm_ref("习题2A.3"))
        self.assertEqual(_norm_ref("习题12"), "ex:12")
        self.assertEqual(_norm_ref("习题2A.7(a)"), "ex:7")

    def test_non_exercise_refs_unchanged_behaviour(self):
        self.assertEqual(_norm_ref("例2.14"), _norm_ref("例 2.14"))
        self.assertEqual(_norm_ref("结论5.27(a)"), _norm_ref("结论5.27"))
        self.assertEqual(_norm_ref("第3题"), _norm_ref("3"))


if __name__ == "__main__":
    unittest.main()
