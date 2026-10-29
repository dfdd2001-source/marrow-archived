#!/usr/bin/env python3
"""基线扩建候选的核实：机械比对 + AI 对照原文裁决。

核实不是"做题"，是"对文本"——检查编号是否真实存在于原书、内容转述是否忠实。
三档策略（能机械核对的绝不浪费 AI）：
1. machine_verified —— 候选自带 verify 且 check_case 重算 PASS（⚙ 标记）
2. source_match     —— source_ref 在原文中存在，且内容与原文邻近窗口相似度达标
3. ai_judge         —— 其余交 AI 对照原文逐条裁决，要求引用原文证据

用法:
  python3 scripts/verify_candidates.py            # 核实并写出判定结果
  python3 scripts/verify_candidates.py --merge    # 核实后把通过项并入 cores/（带 verified_by 溯源）
产物: docs/baseline-expansion-candidates.json（结构化判定）
"""
import argparse
import difflib
import glob
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

SIM_PASS = 0.55   # 相似度达标线
SIM_SUSPECT = 0.30  # 低于此且 ref 存在，交 AI；ref 不存在直接 suspect

SECTIONS = ["ladr-5a", "ladr-5b", "ladr-3a-3c"]


def best_blind_core(section):
    """取该节最新一次盲测的最优 core（best/ 或单次顶层）。"""
    dirs = sorted(glob.glob(os.path.join(ROOT, "harness", "results", "openai", section, "*")))
    for d in reversed(dirs):
        for rel in ("best/core.json", "core.json"):
            p = os.path.join(d, rel)
            if os.path.exists(p):
                return json.load(open(p, encoding="utf-8"))
    return None


def derive_candidates(section, baseline, blind):
    """盲测相对基线的'基线外新增'（案例按 ref 归一、算法按名称归一）。"""
    def norm(s):
        return re.sub(r"[^\w]+", "", str(s)).lower()

    b_refs = {norm(c.get("source_ref", "")) for c in baseline.get("cases", []) + baseline.get("cases_practice", [])}
    b_algos = {norm(a.get("name", "")) for a in baseline.get("algorithms", [])}
    out = []
    for c in blind.get("cases", []) + blind.get("cases_practice", []):
        if norm(c.get("source_ref", "")) not in b_refs:
            out.append({"type": "case", "role": c.get("role"), "source_ref": c.get("source_ref"),
                        "content": c.get("content", ""), "verify": c.get("verify")})
    for a in blind.get("algorithms", []):
        if norm(a.get("name", "")) not in b_algos:
            out.append({"type": "algorithm", "source_ref": a.get("source_ref"),
                        "name": a.get("name"), "content": a.get("statement", "")})
    return out


def ref_in_source(ref, text):
    """编号是否出现在原文（容忍空格/全角括号差异，"第N题"改写为".N"）。"""
    r = re.sub(r"[^\w.()（）]", "", str(ref))
    r = re.sub(r"第(\d+)题", r".\1", r)
    if not r:
        return False
    pat = re.escape(r).replace(r"\(", "").replace(r"\)", "").replace("（", "").replace("）", "")
    digits = re.search(r"\d+\.\d+", r)
    if digits:  # 例5.15 / 定义3.31 / 结论5.27(a) —— 只按编号数字找
        return digits.group(0) in text
    # 习题N：按题号找（习题块里以题号开头的行）
    m = re.search(r"(\d+)$", r)
    return bool(m and re.search(rf"(?m)^\s*{m.group(1)}[\s．.]", text))


def content_similarity(content, text):
    """内容与原文的最相似窗口比例（先用内容锚点定位，避免全文本滑窗）。
    注意两侧都要 NFKC：PDF 文本的变量是数学斜体（𝑈𝑇），AI 写的是 ASCII（UT）。"""
    content = re.sub(r"\s+", "", unicodedata.normalize("NFKC", content))
    if len(content) < 8:
        return 0.0
    anchors = [content[i:i + 12] for i in range(0, min(len(content), 48), 12)]
    best_pos, best = 0, 0.0
    for a in anchors:
        p = text.find(a)
        if p >= 0:
            window = text[max(0, p - 200): p + len(content) + 400]
            r = difflib.SequenceMatcher(None, content, re.sub(r"\s+", "", window)).ratio()
            if r > best:
                best, best_pos = r, p
    if best == 0.0:  # 锚点没命中，退化为长片段查找
        frag = content[8:40]
        p = text.find(frag)
        if p >= 0:
            window = re.sub(r"\s+", "", text[max(0, p - 200): p + len(content) + 400])
            best = difflib.SequenceMatcher(None, content, window).ratio()
    return round(best, 3)


def ai_judge(harness, section_meta, items, source_text):
    """AI 对照原文逐条裁决，要求引用原文证据。返回 {index: verdict}。"""
    from prompts import REGISTRY_SPEC  # noqa: F401  (占位说明：本判断与注册表无关)
    listing = json.dumps([
        {"i": i, "source_ref": it["source_ref"], "content": it["content"][:400]}
        for i, it in enumerate(items)], ensure_ascii=False, indent=1)
    system = (
        "你是严格的原书核对员。给你某节的原文和一组从该节提取的候选条目，"
        "逐条判断：(1) source_ref 指向的编号条目是否真实存在于原文；"
        "(2) content 是否忠实转述原文（不缺关键条件、不改题意；允许简洁化措辞）。"
        "判断必须基于给出的原文，必要时在 evidence 里引用原文片段。"
        '输出单个 JSON：{"verdicts": [{"i": 序号, "exists": true/false, '
        '"faithful": true/false, "evidence": "原文片段或问题说明"}]}，不要输出其他内容。'
    )
    user = (f"## 章节\n{section_meta['section']}\n\n## 原文\n{source_text}\n\n"
            f"## 待核对条目\n{listing}")
    out = harness.complete_json([
        {"role": "system", "content": system}, {"role": "user", "content": user}])
    verdicts = {}
    for v in (out.get("verdicts", []) if isinstance(out, dict) else []):
        try:
            verdicts[int(v["i"])] = v
        except (KeyError, TypeError, ValueError):
            continue
    return verdicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true", help="把通过项并入 cores/（带 verified_by）")
    ap.add_argument("--skip-ai", action="store_true", help="只做机械比对，AI 判断项留待处理")
    args = ap.parse_args()

    results = {}
    totals = {"machine_verified": 0, "source_match": 0, "ai_pass": 0, "ai_fail": 0, "suspect": 0}

    for section in SECTIONS:
        baseline = json.load(open(os.path.join(ROOT, "cores", f"{section}.json"), encoding="utf-8"))
        blind = best_blind_core(section)
        if not blind:
            print(f"[跳过] {section}: 无盲测结果")
            continue
        src_path = os.path.join(ROOT, "harness", "sources", f"{section}.txt")
        if not os.path.exists(src_path):
            print(f"[跳过] {section}: 无原文文本")
            continue
        text = unicodedata.normalize("NFKC", open(src_path, encoding="utf-8").read())
        text_ns = re.sub(r"\s+", "", text)
        section_meta = {"book": baseline["source"]["book"], "section": baseline["source"]["section"]}

        items = derive_candidates(section, baseline, blind)
        print(f"{section}: 候选 {len(items)} 条")
        totals = {"machine_verified": 0, "source_match": 0, "ai_pass": 0, "ai_fail": 0, "suspect": 0}

        # 第一档：机器验证过
        # 第二档：机械比对
        need_ai = []
        for i, it in enumerate(items):
            if it["type"] == "case" and it.get("verify"):
                from run_validation import check_case
                status, _ = check_case(it)
                if status == "PASS":
                    it["verdict"] = "machine_verified"
                    totals["machine_verified"] += 1
                    continue
            ref_ok = ref_in_source(it["source_ref"], text)
            sim = content_similarity(it["content"], text_ns)
            it["ref_exists"] = ref_ok
            it["similarity"] = sim
            if ref_ok and sim >= SIM_PASS:
                it["verdict"] = "source_match"
                totals["source_match"] += 1
            elif not ref_ok:
                # 声称的编号在原文中找不到——机器无法核对，直接标疑
                it["verdict"] = "suspect"
                totals["suspect"] += 1
            else:
                # ref 存在但内容相似度低：AI 转述属正常现象，交 AI 对照原文判断
                it["verdict"] = "ai_judge"
                need_ai.append(i)

        # 第三档：AI 对照原文裁决
        if need_ai and not args.skip_ai:
            from openai_compat import OpenAICompatHarness
            harness = OpenAICompatHarness(
                base_url=os.environ.get("AGNES_BASE_URL", "https://api.agnes-ai.com/api/v1"),
                model="agnes-3.0-flash", api_key_env="AGNES_API_KEY", timeout=900)
            verdicts = ai_judge(harness, section_meta, [items[i] for i in need_ai], text)
            for idx, v in verdicts.items():
                it = items[need_ai[idx]]
                it["ai_evidence"] = str(v.get("evidence", ""))[:200]
                if v.get("exists") and v.get("faithful"):
                    it["verdict"] = "ai_pass"
                    totals["ai_pass"] += 1
                else:
                    it["verdict"] = "ai_fail"
                    totals["ai_fail"] += 1
        elif need_ai:
            for i in need_ai:
                totals["suspect"] += 1
                items[i]["verdict"] = "suspect"

        results[section] = items
        print(f"  判定: " + ", ".join(f"{k}={v}" for k, v in totals.items()))

    with open(os.path.join(ROOT, "docs", "baseline-expansion-candidates.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    # ---- 合并 ----
    if args.merge:
        merged = 0
        for section, items in results.items():
            path = os.path.join(ROOT, "cores", f"{section}.json")
            core = json.load(open(path, encoding="utf-8"))
            for it in items:
                if it["verdict"] not in ("machine_verified", "source_match", "ai_pass"):
                    continue
                entry = {"verified_by": "ai-review-v1"}
                if it["type"] == "case":
                    # practice 统一进 cases_practice（无则建键），避免混进 PWA 的"例题"展示区
                    key = "cases_practice" if it.get("role") == "practice" else "cases"
                    entry.update({"id": f"ai_{abs(hash(it['source_ref'])) % 10**6}",
                                  "content": it["content"], "source_ref": it["source_ref"],
                                  "role": it.get("role", "practice"),
                                  "is_verbatim": bool(it.get("verify"))})
                    if it.get("verify"):
                        entry["verify"] = it["verify"]
                else:
                    key = "algorithms"
                    entry.update({"id": f"ai_{abs(hash(it['name'])) % 10**6}",
                                  "name": it["name"], "statement": it["content"],
                                  "source_ref": it["source_ref"], "executable": False})
                pool = core.setdefault(key, [])
                norm = lambda s: re.sub(r"[^\w]+", "", str(s)).lower()  # noqa: E731
                dup = any(norm(e.get("source_ref", "")) == norm(it["source_ref"]) for e in pool)
                if not dup:
                    pool.append(entry)
                    merged += 1
            json.dump(core, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"已合并 {merged} 条进 cores/（verified_by=ai-review-v1）")

    print("总计:", json.dumps(totals, ensure_ascii=False))


if __name__ == "__main__":
    main()
