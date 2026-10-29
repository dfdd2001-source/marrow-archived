"""DeepSeek harness —— 走 OpenAI 兼容接口调用 deepseek-chat / deepseek-reasoner。

依赖：仅 Python 标准库（urllib）。需要 DEEPSEEK_API_KEY 环境变量（或 --api-key）。
每次调用的原始响应完整保留（harness.last_usage / run_meta.json），供成本核算与追溯。
"""
import json
import os
import urllib.error
import urllib.request

from base import BaseHarness
from prompts import build_messages

API_URL = "https://api.deepseek.com/chat/completions"


class DeepSeekHarness(BaseHarness):
    name = "deepseek"

    def __init__(self, model="deepseek-chat", temperature=0.1, api_key=None, related_core_ids=None):
        self.model = model
        self.temperature = temperature
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise RuntimeError("缺少 API key：请设置 DEEPSEEK_API_KEY 环境变量")
        self.related_core_ids = related_core_ids or []
        self.last_usage = None
        self.raw_response = None

    def extract(self, source_text, section_meta, schema_json):
        messages = build_messages(source_text, section_meta, schema_json, self.related_core_ids)
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 8192,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        req = urllib.request.Request(API_URL, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"DeepSeek API 调用失败 HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:500]}") from e
        self.raw_response = data
        self.last_usage = data.get("usage")
        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"返回内容不是合法 JSON（前200字符: {content[:200]!r}）") from e
