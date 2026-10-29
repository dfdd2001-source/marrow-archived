"""Marrow harness 抽象接口。

一个 harness = 一个能独立完成"章节原文 -> core JSON"提取的执行体。
评测器(evaluate.py)只依赖 extract() 接口，换 harness 不换评测器。

注意：本目录模块按脚本方式运行（经 run_eval.py 注入 sys.path），
新增 harness 请继承 BaseHarness 并放进本目录，参照 deepseek.py。
"""


class BaseHarness:
    name = "base"

    def extract(self, source_text, section_meta, schema_json):
        """source_text: 章节原文文本; section_meta: {book, section, page_range};
        schema_json: core schema 原文（注入 prompt 用，单一事实来源是 docs/marrow-core-schema-v1.json）。
        返回符合 schema 的 dict。抛异常视为本次提取失败。"""
        raise NotImplementedError


class FileHarness(BaseHarness):
    """离线模式：从已有 JSON 文件读取提取结果。
    用途：评测框架自测（基线自评应满分）、复评历史产物、CI 里跑评测器回归。"""

    name = "file"

    def __init__(self, path):
        self.path = path

    def extract(self, source_text, section_meta, schema_json):
        import json
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)
