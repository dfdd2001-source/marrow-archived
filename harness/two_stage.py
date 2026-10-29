"""两段式包装器：第一段清点编号清单，第二段带清单做完整提取。

动机：单段提取里"算法条目漏提/编号不精确"是实测最弱、波动最大的维度（5B 算法召回
在 0%~100% 之间跳）。第一段只做清点这一件事，把完整清单注入第二段 prompt 作为
覆盖检查清单，用分工压住方差。盲测保证：两段 prompt 均不含任何基线内容。

用法（run_eval.py）: --two-stage 开关，仅支持 openai 兼容 inner。
"""
import json

from base import BaseHarness
from prompts import build_inventory_messages, build_messages


def _merge_usage(u1, u2):
    """合并两阶段的 token 用量（求和，缺字段容忍）。"""
    if not u1:
        return u2
    if not u2:
        return u1
    merged = dict(u2)
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if k in u1 or k in u2:
            merged[k] = (u1.get(k) or 0) + (u2.get(k) or 0)
    return merged


class TwoStageHarness(BaseHarness):
    name = "two-stage"

    def __init__(self, inner):
        self.inner = inner  # 任何暴露 complete_json() 的 harness（当前: OpenAICompatHarness）
        self.last_usage = None
        self.raw_response = None
        self.inventory = None

    def extract(self, source_text, section_meta, schema_json):
        # 第一段：清点
        inv = self.inner.complete_json(build_inventory_messages(source_text, section_meta))
        stage1_usage = self.inner.last_usage
        self.inventory = inv
        # 第二段：带清单完整提取
        core = self.inner.complete_json(build_messages(
            source_text, section_meta, schema_json,
            getattr(self.inner, "related_core_ids", None),
            coverage_checklist=json.dumps(inv, ensure_ascii=False, indent=1)))
        self.last_usage = _merge_usage(stage1_usage, self.inner.last_usage)
        self.raw_response = {"stage1_inventory": inv,
                             "stage2_raw": self.inner.raw_response}
        return core

    def complete_json(self, messages):
        """透传给包装器（如生成-检验阶段）复用 inner 的对话能力。"""
        return self.inner.complete_json(messages)
