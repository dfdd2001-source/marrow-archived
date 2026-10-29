"""promote_core.build_verified_core 的回归测试。

重点守护三个曾存在的 bug：
1. 组装错位：任何条目被排除后，同类别后续条目错位取到前一条源内容；
2. 机检通过的 verify 声明未随条目下发（组装层无条件剥离）；
3. 机检未通过的案例连 candidate_answer 一起剥离（不得带"已验证"标记下发）。

测试注入 SIM_PASS=0：被测对象是核实后的组装/过滤/对账逻辑，不是
content_similarity 的启发式（difflib 对重复文本有 autojunk 塌缩，不适合做夹具）。
SIM_PASS=0 时"ref 在原文中"即判 source_match，"ref 不在"仍判 suspect，
由此可确定性地构造排除场景，全程不触发 AI 调用。
"""
import os
import sys
import platform  # noqa: F401  # 先钉住标准库，防止 backend/platform.py 在 sys.path 上遮蔽它
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "scripts"), os.path.join(ROOT, "harness"),
          os.path.join(ROOT, "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

import promote_core  # noqa: E402

# 内容长度无关紧要（阈值置 0），但保持与真实条目相似的形态
def _long(s):
    return (s + "。") * 40


SOURCE_TEXT = (
    "第1章 1A节：测试\n"
    "定义1.1 " + _long("alpha条目的原文表述") + "\n"
    "定义1.3 " + _long("gamma条目的原文表述") + "\n"
    "例1.1 " + _long("例111的原文题设与解") + "\n"
    "例1.2 " + _long("例112的原文题设与解") + "\n"
    "习题块\n"
    "1 " + _long("例113的原文题设") + "\n"
)


def _blind_core():
    return {
        "topic": "第1章 1A节：测试",
        "source": {"book": "测试书", "section": "第1章 1A节：测试", "page_range": ""},
        "status": "extracted_unverified",
        "structure": {"nodes": ["定义1.1"], "edges": []},
        "dictionary": [
            {"term": "术语甲", "definition": _long("alpha条目的原文表述"), "source_ref": "定义1.1"},
            # 定义1.9 不存在于原文 → suspect → 排除（触发旧错位 bug 的关键场景）
            {"term": "术语乙", "definition": _long("beta条目凭空捏造的表述"), "source_ref": "定义1.9"},
            {"term": "术语丙", "definition": _long("gamma条目的原文表述"), "source_ref": "定义1.3"},
        ],
        "algorithms": [
            {"id": "alg1", "name": "规则甲", "statement": _long("alpha条目的原文表述"),
             "source_ref": "定义1.1", "executable": True},
        ],
        "cases": [
            # 例1.1：机检 PASS → verify 应保留（回归 bug 2）
            {"id": "c1", "content": _long("例111的原文题设与解"), "source_ref": "例1.1",
             "role": "validation", "is_verbatim": True,
             "verify": {"function": "dot_product", "args": {"u": [1, 2], "v": [3, 4]},
                        "expected": 11}},
            # 例1.2：无 verify → 照常保留内容
            {"id": "c2", "content": _long("例112的原文题设与解"), "source_ref": "例1.2",
             "role": "validation", "is_verbatim": True},
            # 习题1：机检 FAIL + 带候选答案 → verify 剥离、答案一并剥离（回归 bug 3）
            {"id": "c3", "content": _long("例113的原文题设"), "source_ref": "习题1",
             "role": "practice", "is_verbatim": False,
             "candidate_answer": "错误答案", "answer_verified": True,
             "verify": {"function": "dot_product", "args": {"u": [1], "v": [1]},
                        "expected": 999}},
        ],
    }


class BuildVerifiedCoreTest(unittest.TestCase):
    def setUp(self):
        with patch.object(promote_core, "SIM_PASS", 0.0):
            self.out, self.stats = promote_core.build_verified_core(_blind_core(), SOURCE_TEXT)

    def test_dictionary_alignment(self):
        # 旧 bug 下：术语甲、术语乙（错位取到中间项）；修复后应为甲、丙
        terms = [d["term"] for d in self.out["dictionary"]]
        self.assertEqual(terms, ["术语甲", "术语丙"])

    def test_case_alignment_and_verify_retained(self):
        # c1 内容必须仍是例1.1 的内容（旧 bug 会错位），且机检通过的 verify 保留
        self.assertEqual(len(self.out["cases"]), 2)
        c1 = next(c for c in self.out["cases"] if c["id"] == "c1")
        self.assertIn("例111", c1["content"])
        self.assertEqual(c1["verify"]["expected"], 11)
        self.assertEqual(c1["verify"]["function"], "dot_product")

    def test_failed_verify_strips_answer_too(self):
        self.assertEqual(len(self.out["cases_practice"]), 1)
        c3 = self.out["cases_practice"][0]
        self.assertNotIn("verify", c3)
        self.assertNotIn("candidate_answer", c3)
        self.assertNotIn("answer_verified", c3)
        self.assertIn("verify_note", c3)

    def test_plain_case_untouched(self):
        c2 = next(c for c in self.out["cases"] if c["id"] == "c2")
        self.assertNotIn("verify", c2)
        self.assertNotIn("candidate_answer", c2)
        self.assertEqual(c2["content"], _long("例112的原文题设与解"))

    def test_every_entry_traced(self):
        for pool in ("dictionary", "algorithms", "cases", "cases_practice"):
            for entry in self.out[pool]:
                self.assertEqual(entry.get("verified_by"), "ai-review-v1")

    def test_structure_preserved_as_dict(self):
        self.assertEqual(self.out["structure"], {"nodes": ["定义1.1"], "edges": []})

    def test_status_and_stats(self):
        self.assertEqual(self.out["status"], "extracted_verified")
        self.assertGreater(self.stats["pass"], 0)
        self.assertEqual(self.stats.get("stripped"), 1)


if __name__ == "__main__":
    unittest.main()
