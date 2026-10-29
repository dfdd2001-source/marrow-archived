# harness/ —— 可插拔提取执行层 + 盲测评测框架

回答一个此前悬置的问题：**换一个自动化 harness 独立提取，质量能达到人工水平吗？**
评测器把这个问题变成可复现的数字，而不是印象分。

## 目录

- `base.py` —— harness 抽象接口 + FileHarness（离线读 JSON，用于自测/复评）
- `prompts.py` —— 提取 prompt（schema + 校验机制 + 硬性规则）。**盲测保证：不含任何基线内容**
- `deepseek.py` —— DeepSeek 适配器（OpenAI 兼容接口，纯标准库）
- `evaluate.py` —— 评测器：schema 完整性 / verify 重算 / 基线召回对比
- `run_eval.py` —— CLI 入口
- `sources/` —— 章节原文 txt（版权材料，gitignore，不入库）
- `results/` —— 每次评测产物（core.json / run_meta.json / scorecard.json / scorecard.md），不入库

## 用法

### Agnes AI（新加坡免费网关 agnes-ai.com，当前默认实验 harness）

免费额度、免费 API key，OpenAI 兼容风格。已探测确认 base URL：
`https://api.agnes-ai.com/api/v1`（/models 需 Bearer key，401 = 端点在等 key）。

```bash
# 0. agnes-ai.com 注册 → 创建 API key → 项目根目录 .env 写入：AGNES_API_KEY=sk-xxxx
# 1. 列出网关可用模型，选一个强聊天模型（DeepSeek-V3.x / GPT / Claude 系皆可）
python3 harness/run_eval.py --harness openai --list-models \
    --base-url https://api.agnes-ai.com/api/v1 --api-key-env AGNES_API_KEY

# 2. 盲测单节
python3 harness/run_eval.py --harness openai \
    --base-url https://api.agnes-ai.com/api/v1 --api-key-env AGNES_API_KEY \
    --model <模型名> --source harness/sources/ladr-5a.txt \
    --section "第5章 5A节：不变子空间" --page-range "PDF第126-133页" \
    --section-id ladr-5a --baseline cores/ladr-5a.json \
    --related-core-ids ladr-3a-3c,ladr-5b
```

注：若网关不支持 `response_format=json_object`，适配器自动降级重试；
若鉴权方式不是标准 Bearer，报错信息会带 HTTP 码和响应体，照着调适配器即可。

### 其他 harness

```bash
# DeepSeek（需 DEEPSEEK_API_KEY）
python3 harness/run_eval.py --harness deepseek --source harness/sources/ladr-5a.txt \
    --section "第5章 5A节：不变子空间" --section-id ladr-5a --baseline cores/ladr-5a.json

# 离线复评 / 评测器自测（基线自评应 gate PASS + 召回 100%）
python3 harness/run_eval.py --harness file --from-file cores/ladr-5a.json \
    --section-id ladr-5a --baseline cores/ladr-5a.json

# CI 门禁（所有基线 core 的 verify 案例必须 PASS）
python3 scripts/validate_all_cores.py
```

## 评测维度与门槛

| 维度 | 内容 | 是否门槛 |
|---|---|---|
| schema 完整性 | 必填字段/枚举（schema v1） | 是 |
| 机器验证 | `cases[].verify` 声明交给校验引擎重算，FAIL/ERROR 即不通过 | 是 |
| 基线召回 | 词典按 term、算法按 name、案例按 source_ref 对比 | 否（参考） |
| 人工抽查 | 基线外新增条目（忠实还是幻觉）+ 无 verify 案例的 source_ref 抽查 | 人工 |

**决策门槛（Phase 2 harness 评测，对齐产品文档路线图）**：同一 harness 在 ≥2 个风格不同的
小节上，gate 全过、召回可观、人工修补时间可接受（建议 ≤15 分钟/core），才谈生产化。
代价数据（token 用量在 run_meta.json 里）每次自动记录，用于核算单章成本。

## 新增一个 harness

继承 `BaseHarness`（见 `base.py`），实现 `extract(source_text, section_meta, schema_json)`，
放进本目录，run_eval.py 加一个 choice 即可。评测器不用动。
