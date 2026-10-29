#!/usr/bin/env python3
"""为存量 core 的习题批量回填机器验证答案（两段式：提案 → 人工核准 → 合并）。

为什么两段：check_case 只能验证"声明为真"，无法验证"答案文本与声明一致"——
首轮回填曾因此混入答案错误但声明可过的条目（如 det=3 为真、特征值却答错），
后经人工全量复核剥离。所以本脚本默认只产出提案文件，绝不直接写 cores/。

用法:
  python3 scripts/backfill_verify.py                # 生成提案 docs/backfill-proposals.json
  #   人工逐条审阅，把认可条目加 "approved": true（核查：答案数值是否真被 verify 蕴含）
  python3 scripts/backfill_verify.py --merge        # 把 approved 条目并入 cores/（合并前再过一次机检门）
  python3 scripts/backfill_verify.py --dry-run      # 只统计现状，不调 API
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "harness"), os.path.join(ROOT, "backend"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from openai_compat import OpenAICompatHarness  # noqa: E402
from solve import solve_practice  # noqa: E402
from envtools import load_env  # noqa: E402
from run_validation import check_case  # noqa: E402


def count_state(core):
    practice = len(core.get("cases_practice", []))
    with_answer = sum(1 for c in core.get("cases_practice", []) if c.get("answer_verified"))
    return practice, with_answer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只处理这一节（如 ladr-1a）")
    ap.add_argument("--model", default="agnes-3.0-flash")
    ap.add_argument("--dry-run", action="store_true", help="只统计现状，不调 API")
    ap.add_argument("--merge", action="store_true", help="把人工核准的提案并入 cores/")
    args = ap.parse_args()
    if args.merge:
        merge_proposals()
        return

    paths = sorted(glob.glob(os.path.join(ROOT, "cores", "*.json")))
    if args.only:
        paths = [p for p in paths if os.path.basename(p)[:-5] == args.only]
    if not paths:
        sys.exit("没有匹配的 core 文件")

    if args.dry_run:
        for path in paths:
            core = json.load(open(path, encoding="utf-8"))
            practice, with_answer = count_state(core)
            print(f"{os.path.basename(path)[:-5]}: 习题 {practice}，已有机检答案 {with_answer}")
        return

    env = load_env()
    if "AGNES_API_KEY" not in env:
        sys.exit("缺少 AGNES_API_KEY（.env）")
    harness = OpenAICompatHarness(
        base_url=env.get("AGNES_BASE_URL", "https://api.agnes-ai.com/api/v1"),
        model=args.model, api_key=env.get("AGNES_API_KEY"))

    totals = {"sections": 0, "proposals": 0, "verified": 0, "api_fail": 0}
    proposals = []
    for path in paths:
        sid = os.path.basename(path)[:-5]
        core = json.load(open(path, encoding="utf-8"))
        practice, done = count_state(core)
        if practice == 0 or practice == done:
            print(f"[跳过] {sid}: 习题 {practice}，已全覆盖 {done}")
            continue
        meta = {"book": core["source"]["book"], "section": core["source"]["section"],
                "page_range": core["source"].get("page_range", "")}
        try:
            core, stats = solve_practice(harness, core, meta)
        except Exception as e:
            totals["api_fail"] += 1
            print(f"[失败] {sid}: {str(e)[:140]}")
            continue
        totals["sections"] += 1
        totals["proposals"] += stats.get("proposed", 0)
        totals["verified"] += stats.get("verified", 0)
        for x in core.get("cases_practice", []):
            if x.get("answer_verified"):
                proposals.append({
                    "core_id": sid, "source_ref": x.get("source_ref"),
                    "content": x.get("content", ""), "answer": x.get("candidate_answer"),
                    "verify": x.get("verify"), "approved": False,
                })
        print(f"[提案] {sid}: 提议 {stats.get('proposed', 0)}，通过机检 {stats.get('verified', 0)}")

    out_path = os.path.join(ROOT, "docs", "backfill-proposals.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(proposals, f, ensure_ascii=False, indent=1)
    print("\n== 汇总 ==")
    print(f"处理 {totals['sections']} 节，提案 {totals['proposals']}（机检通过 {totals['verified']}），"
          f"API 失败 {totals['api_fail']} 节")
    print(f"提案已写出: {out_path}")
    print("下一步：人工逐条核查「答案数值是否真被 verify 蕴含」，认可后加 \"approved\": true，再跑 --merge")


def merge_proposals():
    """把人工核准（approved=true）的提案并入 cores/；合并前再过一次机检门。"""
    from run_validation import check_case
    path = os.path.join(ROOT, "docs", "backfill-proposals.json")
    if not os.path.exists(path):
        sys.exit("没有提案文件 docs/backfill-proposals.json")
    proposals = json.load(open(path, encoding="utf-8"))
    approved = [p for p in proposals if p.get("approved")]
    print(f"提案 {len(proposals)} 条，人工核准 {len(approved)} 条")
    by_core = {}
    for p in approved:
        status, detail = check_case({"verify": p["verify"]})
        if status != "PASS":
            print(f"  [拒] {p['core_id']} {p['source_ref']}: 机检未过（{detail[:80]}）")
            continue
        by_core.setdefault(p["core_id"], []).append(p)
    merged = 0
    for sid, items in by_core.items():
        cpath = os.path.join(ROOT, "cores", f"{sid}.json")
        core = json.load(open(cpath, encoding="utf-8"))
        for it in items:
            for x in core.get("cases_practice", []):
                if x.get("source_ref") == it["source_ref"] and not x.get("answer_verified"):
                    x["candidate_answer"] = it["answer"]
                    x["verify"] = it["verify"]
                    x["answer_verified"] = True
                    merged += 1
        json.dump(core, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已并入 {merged} 条（verified_by 流程：AI 提案 + 机检 + 人工核准）")


if __name__ == "__main__":
    main()
