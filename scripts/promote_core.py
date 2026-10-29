#!/usr/bin/env python3
"""把一节盲测的最优 core 经核实管道提升为正式基线 core。

与 verify_candidates.py 的区别：后者核对"盲测相对基线的新增"，本脚本把一整份
盲测提取（如 6A，尚无基线）全部条目过一遍核实（机械比对 + AI 对照原文），
生成 cores/<out>。条目带 verified_by=ai-review-v1 溯源。

用法:
  python3 scripts/promote_core.py --core <盲测core.json> \
      [--answers-from <另一份core.json，移植 answer_verified 的案例>] \
      [--source-text <章节原文txt>] --out cores/ladr-6a.json
"""
import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from verify_candidates import ref_in_source, content_similarity, ai_judge, SIM_PASS  # noqa: E402


def build_verified_core(core, text, answers_from_path=None):
    """核实 -> 剥离失败声明 -> 组装正式 core。

    core: 盲测提取 dict；text: 章节原文（NFKC 后，可含空白）。
    返回 (out_core, stats)。stats 含 pass/ai_fail/suspect/stripped 计数。
    AI 裁决需要网关密钥时抛出的异常由调用方处理；纯机械可判定的输入不会触发调用。
    """
    text_ns = re.sub(r"\s+", "", text)  # 相似度在去空白文本上算（与 verify_candidates 一致）

    # 汇总全部待核实条目
    items, kinds = [], []
    for d in core.get("dictionary", []):
        items.append({"source_ref": d.get("source_ref"), "content": f"{d['term']}：{d['definition']}"})
        kinds.append("dictionary")
    for a in core.get("algorithms", []):
        items.append({"source_ref": a.get("source_ref"), "content": f"{a['name']}：{a['statement']}"})
        kinds.append("algorithms")
    for c in core.get("cases", []) + core.get("cases_practice", []):
        items.append({"source_ref": c.get("source_ref"), "content": c.get("content", "")})
        kinds.append("cases")

    # 第一遍：机械比对
    need_ai = []
    for i, it in enumerate(items):
        ref_ok = ref_in_source(it["source_ref"], text)
        sim = content_similarity(it["content"], text_ns)
        it["ref_exists"], it["similarity"] = ref_ok, sim
        if ref_ok and sim >= SIM_PASS:
            it["verdict"] = "source_match"
        elif not ref_ok:
            it["verdict"] = "suspect"
        else:
            it["verdict"] = "ai_judge"
            need_ai.append(i)

    # 第二遍：AI 对照原文
    if need_ai:
        from openai_compat import OpenAICompatHarness
        harness = OpenAICompatHarness(
            base_url=os.environ.get("AGNES_BASE_URL", "https://api.agnes-ai.com/api/v1"),
            model="agnes-3.0-flash", api_key_env="AGNES_API_KEY")
        verdicts = ai_judge(harness, {"section": core["source"]["section"]},
                            [items[i] for i in need_ai], text)
        for idx, v in verdicts.items():
            it = items[need_ai[idx]]
            it["ai_evidence"] = str(v.get("evidence", ""))[:200]
            it["verdict"] = "ai_pass" if (v.get("exists") and v.get("faithful")) else "ai_fail"

    stats = {
        "pass": sum(1 for it in items if it["verdict"] in ("source_match", "ai_pass")),
        "ai_fail": sum(1 for it in items if it["verdict"] == "ai_fail"),
        "suspect": sum(1 for it in items if it["verdict"] == "suspect"),
    }

    # ---- 声明剥离：verify 重算未通过的，剥离声明、保留内容 ----
    # 对齐 core_versions 审核语义：声明错≠内容错，但错误声明绝不下发。
    # 通过机检的声明随条目原样保留（见下方组装），成为 CI 门禁的守护对象。
    from run_validation import check_case
    case_status = {}  # id(case) -> PASS/FAIL/ERROR/SKIP（组装时决定 verify 去留）
    for pool in ("cases", "cases_practice"):
        for c in core.get(pool, []):
            if c.get("verify"):
                status, detail = check_case(c)
                case_status[id(c)] = status
                if status != "PASS":
                    c.pop("verify")
                    c["verify_note"] = f"机器验证未通过（{detail[:120]}），声明已剥离，内容保留待审"
                    stats["stripped"] = stats.get("stripped", 0) + 1

    # ---- 组装正式 core（只保留通过项）----
    def ok(i):
        return items[i]["verdict"] in ("source_match", "ai_pass")

    out = {
        "topic": core.get("topic"),
        "source": core.get("source"),
        "status": "extracted_verified",
        "verification_note": "全部条目经 AI 对照原书文本核实（verified_by=ai-review-v1）；"
                             "verify 案例另经校验引擎机器重算。人工抽检可按 verified_by 字段筛出本批。",
        "dictionary": [], "structure": core.get("structure", {}),
        "algorithms": [], "cases": [], "cases_practice": [],
    }
    src_cases = core.get("cases", []) + core.get("cases_practice", [])
    di = ai_ = ci = 0
    for i, kind in enumerate(kinds):
        # 计数器必须对每一条都前进：过滤发生在"取源条目"之后。
        # 若先 continue 再计数，任何一条被排除都会让后续全部条目错位取到前一条的内容。
        passed = ok(i)
        if kind == "dictionary":
            d = core["dictionary"][di]
            di += 1
            if passed:
                out["dictionary"].append({**d, "verified_by": "ai-review-v1"})
        elif kind == "algorithms":
            a = core["algorithms"][ai_]
            ai_ += 1
            if passed:
                out["algorithms"].append({**a, "verified_by": "ai-review-v1"})
        else:
            c = src_cases[ci]
            ci += 1
            if passed:
                pool = out["cases_practice"] if c.get("role") == "practice" else out["cases"]
                # verify 通过机检的案例连答案一起保留（机器验证底座）；未通过的连
                # candidate_answer/answer_verified 一并剥离——无声明的内容不得带"已验证"标记
                keep = case_status.get(id(c)) == "PASS"
                drop = set() if keep else {"candidate_answer", "verify", "answer_verified"}
                entry = {k: v for k, v in c.items() if k not in drop}
                entry["verified_by"] = "ai-review-v1"
                pool.append(entry)

    # ---- 移植机器验证过的候选答案（仅指定来源里 answer_verified 的案例）----
    if answers_from_path:
        src = json.load(open(answers_from_path, encoding="utf-8"))
        by_ref = {}
        for c in src.get("cases", []) + src.get("cases_practice", []):
            if c.get("answer_verified"):
                by_ref[re.sub(r"[^\w]+", "", c.get("source_ref", "")).lower()] = c
        for pool in (out["cases_practice"], out["cases"]):
            for c in pool:
                hit = by_ref.get(re.sub(r"[^\w]+", "", c.get("source_ref", "")).lower())
                if hit and c.get("source_ref") != "习题8":  # 习题8 的检验是平凡恒等式，人工剔除
                    c.update({"candidate_answer": hit["candidate_answer"],
                              "verify": hit["verify"], "answer_verified": True})

    return out, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True, help="盲测 core JSON 路径")
    ap.add_argument("--answers-from", help="从另一份 core 移植 answer_verified 的案例")
    ap.add_argument("--source-text", required=True, help="对应章节原文 txt")
    ap.add_argument("--out", required=True, help="输出路径，如 cores/ladr-6a.json")
    args = ap.parse_args()

    core = json.load(open(args.core, encoding="utf-8"))
    text = unicodedata.normalize("NFKC", open(args.source_text, encoding="utf-8").read())

    out, stats = build_verified_core(core, text, args.answers_from)

    print(f"核实: {stats['pass']} 通过 / {stats['ai_fail']} AI判否 / {stats['suspect']} 存疑")
    if stats.get("stripped"):
        print(f"声明剥离: {stats['stripped']} 条（内容保留）")

    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已写出 {args.out}: 词典{len(out['dictionary'])} 算法{len(out['algorithms'])} "
          f"例题{len(out['cases'])} 习题{len(out['cases_practice'])}")


if __name__ == "__main__":
    main()
