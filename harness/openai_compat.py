"""OpenAI 兼容网关 harness —— Agnes AI、DeepSeek 及任何 /chat/completions 风格端点通用。

用法（经 run_eval.py）:
  --harness openai --base-url https://api.agnes-ai.com/api/v1 \
  --model <模型名> --api-key-env AGNES_API_KEY

Agnes AI（agnes-ai.com，新加坡）已探测确认：base URL 为 https://api.agnes-ai.com/api/v1，
鉴权为 Bearer key；/models 返回 401 说明端点在、等 key 来调。
网关不支持 response_format=json_object 时自动降级重试。
"""
import json
import os
import urllib.error
import urllib.request

from base import BaseHarness
from prompts import build_messages


class OpenAICompatHarness(BaseHarness):
    name = "openai"

    def __init__(self, base_url, model, api_key=None, api_key_env="OPENAI_API_KEY",
                 temperature=0.1, related_core_ids=None, timeout=600, max_tokens=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.api_key = api_key or os.environ.get(api_key_env)
        if not self.api_key:
            raise RuntimeError(f"缺少 API key：请设置 {api_key_env} 环境变量，或在项目根目录 .env 里提供")
        self.related_core_ids = related_core_ids or []
        self.timeout = timeout
        # 推理模型（如 agnes-*-pro）的 reasoning token 也计入 completion 预算，
        # 设小 max_tokens 会导致"推理烧完预算、正文为空"，默认不传、交给服务端。
        self.max_tokens = max_tokens
        self.last_usage = None
        self.raw_response = None

    def _headers(self):
        return {"Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"}

    def list_models(self):
        req = urllib.request.Request(self.base_url + "/models", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"列模型失败 HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:500]}") from e

    def _post_chat(self, payload):
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _parse_content(content):
        text = content.strip()
        if text.startswith("```"):  # 少数模型无视 json mode 外面包代码围栏
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)

    def complete_json(self, messages):
        """单轮对话 -> 解析后的 JSON dict。extract() 与包装器（两段式）共用；
        json mode 不支持时自动降级；content 为空时给出自诊断错误。"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        try:
            data = self._post_chat(payload)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            if e.code == 400 and "response_format" in payload:
                payload.pop("response_format")  # 网关不支持 json mode，降级重试
                data = self._post_chat(payload)
            else:
                raise RuntimeError(f"API 调用失败 HTTP {e.code}: {detail[:500]}") from e
        self.raw_response = data
        self.last_usage = data.get("usage")
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content") or ""
        if not content.strip():
            finish = choice.get("finish_reason")
            raise RuntimeError(
                f"返回 content 为空（finish_reason={finish}, usage={json.dumps(self.last_usage, ensure_ascii=False)}）。"
                "若是 length 截断：推理模型会先烧 reasoning token，请去掉 max_tokens 限制或换非推理模型")
        try:
            return self._parse_content(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"返回内容不是合法 JSON（前200字符: {content[:200]!r}）") from e

    def extract(self, source_text, section_meta, schema_json):
        return self.complete_json(
            build_messages(source_text, section_meta, schema_json, self.related_core_ids))
