#!/usr/bin/env python3
"""Marrow 单章 onboarding 一键流水线。

把已验证的全流程串成一条命令：
  导出文本（自动裁扉页）→ 两段式+求解采样择优 → AI 核实入编
  → related 链接 → CI 门禁 → app 同步 → 成本汇总

用法:
  python3 scripts/marrow_onboard.py --section-id ladr-6c \
      --pdf ~/Desktop/LADR4eChinese.pdf --pages 191-203 \
      --section "第6章 6C节：正交补和最小化问题" \
      --related "ladr-6a:6C 的正交补与正交投影直接使用 6A 的内积、范数与正交定义" \
                "ladr-6b:6C 的最小化问题大量使用 6B 的规范正交基" \
      [--samples 3] [--model agnes-3.0-flash]

依赖: 项目根目录 .env 提供 AGNES_API_KEY（与 AGNES_BASE_URL，可选）。
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from envtools import load_env  # noqa: E402


def trim_divider(path):
    """裁掉章节间扉页/页眉（（第四版）/《线性代数应该这样学》/Axler/页码+章名）。"""
    lines = open(path, encoding="utf-8").read().splitlines()
    while lines:
        last = lines[-1].strip()
        if (not last or "Axler" in last or "（第四版）" in last
                or re.match(r"^\d{1,3}\s+第 ?\d+ ?章", last)):
            lines.pop()
        else:
            break
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section-id", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", required=True, help="如 191-203")
    ap.add_argument("--section", required=True)
    ap.add_argument("--related", nargs="*", default=[],
                    help="related 链接，格式 'core_id:via 说明'")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--model", default="agnes-3.0-flash")
    args = ap.parse_args()

    env = load_env()
    if "AGNES_API_KEY" not in env:
        sys.exit("缺少 AGNES_API_KEY（.env 或环境变量）")
    txt_path = os.path.join(ROOT, "harness", "sources", f"{args.section_id}.txt")
    p1, p2 = args.pages.split("-")
    t0 = time.time()

    # 1. 导出文本
    print("== 1/6 导出文本 ==", flush=True)
    subprocess.run(["pdftotext", "-f", p1, "-l", p2, "-layout", args.pdf, txt_path], check=True)
    trim_divider(txt_path)
    print(f"   {txt_path} ({os.path.getsize(txt_path)} bytes)", flush=True)

    # 2. 采样择优
    print("== 2/6 两段式+求解 采样 ==", flush=True)
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run_eval.py"),
                         "--harness", "openai",
                         "--base-url", env.get("AGNES_BASE_URL", "https://api.agnes-ai.com/api/v1"),
                         "--api-key-env", "AGNES_API_KEY",
                         "--model", args.model, "--samples", str(args.samples),
                         "--two-stage", "--solve-practice",
                         "--source", txt_path, "--section", args.section,
                         "--page-range", f"PDF第{args.pages}页",
                         "--section-id", args.section_id,
                         "--related-core-ids", ",".join(r.split(":")[0] for r in args.related)],
                        env=env).returncode
    if rc != 0:
        # gate 未过不中止：promote 阶段会剥离未通过机检的声明（声明错≠内容错），
        # 最终以入编后的 CI 门禁为准
        print(f"! 采样阶段 gate 未通过（exit {rc}），继续：入编时将剥离失败声明")

    # 3. 定位择优结果
    best = None
    for d in sorted(glob.glob(os.path.join(ROOT, "harness", "results", "openai",
                                           args.section_id, "*")), reverse=True):
        for rel in ("best/core.json", "core.json"):
            p = os.path.join(d, rel)
            if os.path.exists(p):
                best = p
                break
        if best:
            break
    print(f"== 3/6 择优结果: {best} ==", flush=True)

    # 4. AI 核实入编
    print("== 4/6 AI 核实入编 ==", flush=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "promote_core.py"),
                    "--core", best, "--source-text", txt_path,
                    "--out", os.path.join(ROOT, "cores", f"{args.section_id}.json")],
                   env=env, check=True)

    # 5. related 链接（双向）
    print("== 5/6 related 链接 ==", flush=True)
    new_core_path = os.path.join(ROOT, "cores", f"{args.section_id}.json")
    new_core = json.load(open(new_core_path, encoding="utf-8"))
    short = args.section.split("：")[-1]
    new_core.setdefault("related_cores", [])
    for pair in args.related:
        rid, _, via = pair.partition(":")
        new_core["related_cores"].append({"core_id": rid, "via": via})
        rel_path = os.path.join(ROOT, "cores", f"{rid}.json")
        rel = json.load(open(rel_path, encoding="utf-8"))
        rel.setdefault("related_cores", [])
        if not any(r.get("core_id") == args.section_id for r in rel["related_cores"]):
            rel["related_cores"].append(
                {"core_id": args.section_id, "via": f"{short}（{args.section_id}）建立在本节内容之上"})
        json.dump(rel, open(rel_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(new_core, open(new_core_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 6. 门禁（app/cores 是 cores/ 的符号链接，无需拷贝；索引由平台服务重建）
    print("== 6/6 CI 门禁 ==", flush=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate_all_cores.py")], check=True)

    # 成本汇总
    tokens, runs = 0, 0
    for m in glob.glob(os.path.join(ROOT, "harness", "results", "openai",
                                    args.section_id, "*", "run-*", "run_meta.json")):
        u = json.load(open(m, encoding="utf-8")).get("usage") or {}
        tokens += u.get("total_tokens") or 0
        runs += 1
    wall = round(time.time() - t0)
    core = json.load(open(new_core_path, encoding="utf-8"))
    print("\n== onboarding 完成 ==")
    print(f"  {args.section_id}: 词典{len(core.get('dictionary', []))} "
          f"算法{len(core.get('algorithms', []))} "
          f"例题{len(core.get('cases', []))} 习题{len(core.get('cases_practice', []))}")
    print(f"  墙钟 {wall} 秒 | 采样 {runs} 次 | {tokens} tokens（不含核实阶段）")


if __name__ == "__main__":
    main()
