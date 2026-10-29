#!/usr/bin/env python3
"""对账：已发布 core 与其盲测产物的条目配对一致性。

promote_core 曾有一个组装错位 bug：任何条目被核实排除后，同类别后续条目会
错位取到前一条源内容（term 配上前一条的 definition）。promote 组装是 {**d}
浅拷贝、不改内容，因此确定性判据是——

    发布版里的 (term, definition) / (name, statement) / (source_ref, content) 对
    是否原样存在于该节盲测产物中。

对不存在 = 该对是错位拼盘（重灾区），或该 core 经其他路径生成
（verify_candidates --merge / 人工校验——此时结果仅供参考，见 README 的构建路径说明）。

用法: python3 scripts/check_core_alignment.py [core_id ...]   # 缺省扫描全部
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def best_blind_core(section):
    """取该节最新一次盲测的最优 core（best/ 或单次顶层）。"""
    dirs = sorted(glob.glob(os.path.join(ROOT, "harness", "results", "openai", section, "*")))
    for d in reversed(dirs):
        for rel in ("best/core.json", "core.json"):
            p = os.path.join(d, rel)
            if os.path.exists(p):
                return json.load(open(p, encoding="utf-8"))
    return None


def pair_audit(published, blind, label, key_fn):
    """返回 (总数, 配对不在盲测产物中的条目列表)。"""
    blind_pairs = {key_fn(x) for x in blind}
    bad = [x for x in published if key_fn(x) not in blind_pairs]
    return len(published), bad, label


def audit_core(path):
    sid = os.path.basename(path)[:-5]
    core = json.load(open(path, encoding="utf-8"))
    blind = best_blind_core(sid)
    if not blind:
        return sid, None
    checks = [
        pair_audit(core.get("dictionary", []), blind.get("dictionary", []),
                   "词典", lambda d: (d.get("term"), d.get("definition"))),
        pair_audit(core.get("algorithms", []), blind.get("algorithms", []),
                   "算法", lambda a: (a.get("name"), a.get("statement"))),
        pair_audit(core.get("cases", []) + core.get("cases_practice", []),
                   blind.get("cases", []) + blind.get("cases_practice", []),
                   "案例", lambda c: (c.get("source_ref"), c.get("content"))),
    ]
    return sid, checks


def main():
    ids = sys.argv[1:] or sorted(os.path.basename(p)[:-5]
                                 for p in glob.glob(os.path.join(ROOT, "cores", "*.json")))
    dirty = []
    for sid in ids:
        path = os.path.join(ROOT, "cores", f"{sid}.json")
        sid, checks = audit_core(path)
        if checks is None:
            print(f"[跳过] {sid}: 无盲测产物，无法对账")
            continue
        lines, bad_total = [], 0
        for total, bad, label in checks:
            if bad:
                bad_total += len(bad)
                ex = bad[0]
                sample = ex.get("term") or ex.get("name") or ex.get("source_ref")
                lines.append(f"    {label}: {len(bad)}/{total} 对不存在于盲测产物（如 {sample}）")
        if bad_total:
            dirty.append(sid)
            print(f"[错位] {sid}: 共 {bad_total} 对异常")
            print("\n".join(lines))
        else:
            print(f"[对齐] {sid}")
    print("\n== 结论 ==")
    if dirty:
        print(f"{len(dirty)} 个 core 存在配对异常: {', '.join(dirty)}")
        print("注意两种可能：a) core 经人工校验/verify_candidates --merge 构建，本就不由盲测产物组装"
              "（本项目 3a-3c/5a/5b/6a 即如此，属预期差异）；b) promote 错位拼盘。")
        print("区分办法：人工抽查 term↔definition 是否语义配对。流水线重建（marrow_onboard.py）会重新核实。")
    else:
        print("所有可对账 core 的条目配对均与盲测产物一致。")


if __name__ == "__main__":
    main()
