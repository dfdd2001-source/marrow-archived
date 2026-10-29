#!/usr/bin/env python3
"""CI 门禁：cores/ 下所有 core 的 verify 案例重算后不得有 FAIL/ERROR。

SKIP（未声明 verify 或无对应注册函数）允许存在，但会在报告里列出，推动逐步补齐。
用法: python3 scripts/validate_all_cores.py [core.json ...]（缺省扫描 cores/*.json）
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from run_validation import check_case  # noqa: E402


def main():
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, "cores", "*.json")))
    if not paths:
        print("没有找到任何 core 文件")
        sys.exit(1)

    totals = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    failed = False
    for path in paths:
        with open(path, encoding="utf-8") as f:
            core = json.load(f)
        cases = list(core.get("cases", [])) + list(core.get("cases_practice", []))
        print(f"\n=== {core.get('topic', path)} ({os.path.basename(path)}) ===")
        for c in cases:
            status, detail = check_case(c)
            totals[status] = totals.get(status, 0) + 1
            print(f"  [{status}] {c.get('id')} ({c.get('source_ref', '?')}) — {detail}")
            if status in ("FAIL", "ERROR"):
                failed = True

    print(f"\n合计: {totals['PASS']} PASS / {totals['FAIL']} FAIL / "
          f"{totals['ERROR']} ERROR / {totals['SKIP']} SKIP")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
