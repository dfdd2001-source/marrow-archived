"""评测器：对一份提取结果自动打分。

三个自动维度：
1. schema 完整性 —— required 字段/枚举校验（stdlib 实现，评测框架本身零依赖）
2. 机器验证 —— cases[].verify 声明交给校验引擎(backend/run_validation.py)重算
3. 基线对比 —— 与人工校验基线比召回：词典按 term、算法按 name、案例按 source_ref

门槛(gate)只看 1 和 2：schema 错误或 FAIL/ERROR 即不通过。
召回率是参考指标：基线自身也可能不全，盲测多出来的条目只标记人工抽查，不算失败。
本模块依赖 backend 在 sys.path（由 run_eval.py / scripts 注入），不单独运行。
"""
import json
import re

from run_validation import check_case


def _norm(s):
    """宽松归一化：先去掉括号注解（如"线性映射(linear map)"的英文对照），再去掉全部
    非文字字符（空格/标点），小写。避免"格式差异"被误判为"内容缺失"。"""
    s = re.sub(r"[（(][^（）()]*[)）]", "", str(s))
    return re.sub(r"[^\w]+", "", s, flags=re.UNICODE).lower()


def _norm_ref(s):
    """案例/结论 source_ref 归一化："第N题"改写成".N"对齐编号风格差异；
    去掉紧随数字的尾缀字母（"结论5.27(a)"与"结论5.27"视为同一条）。
    习题类引用统一归约到题号：不同代际的提取对习题命名各异
    （基线"习题3"、平台导入"习题2A.3"、盲测"习题2a3"），只按末段题号对齐。"""
    s = str(s)
    if re.match(r"^\s*习题", s):
        nums = re.findall(r"\d+", s)
        if nums:
            return "ex:" + nums[-1]
    s = re.sub(r"第(\d+)题", r".\1", s)
    s = re.sub(r"[^\w]+", "", s).lower()
    return re.sub(r"(?<=\d)[a-z]$", "", s)


def _case_pool(core):
    pool = {}
    for c in list(core.get("cases", [])) + list(core.get("cases_practice", [])):
        if "source_ref" in c:
            pool[_norm_ref(c["source_ref"])] = c
    return pool


def validate_schema(core):
    """返回错误列表；空列表 = 通过。覆盖 schema v1 的必填字段与枚举，不做 JSON Schema 全量实现。"""
    errors = []
    for field in ("topic", "source", "status", "dictionary", "structure", "algorithms", "cases"):
        if field not in core:
            errors.append(f"缺少必填字段: {field}")
    if "source" in core:
        for f in ("book", "section"):
            if f not in core["source"]:
                errors.append(f"source 缺少 {f}")
    status = core.get("status")
    if status and status not in ("draft_generic", "extracted_unverified", "extracted_verified"):
        errors.append(f"status 非法: {status}")
    for i, d in enumerate(core.get("dictionary", [])):
        for f in ("term", "definition", "source_ref"):
            if f not in d:
                errors.append(f"dictionary[{i}] 缺少 {f}")
    for i, e in enumerate(core.get("structure", {}).get("edges", [])):
        for f in ("from", "to", "relation"):
            if f not in e:
                errors.append(f"structure.edges[{i}] 缺少 {f}")
    for i, a in enumerate(core.get("algorithms", [])):
        for f in ("id", "name", "statement", "source_ref"):
            if f not in a:
                errors.append(f"algorithms[{i}] 缺少 {f}")
    cases = list(core.get("cases", [])) + list(core.get("cases_practice", []))
    for i, c in enumerate(cases):
        for f in ("id", "content", "source_ref", "role", "is_verbatim"):
            if f not in c:
                errors.append(f"cases[{i}]({c.get('id', '?')}) 缺少 {f}")
        if c.get("role") not in ("validation", "practice"):
            errors.append(f"cases[{i}]({c.get('id', '?')}) role 非法: {c.get('role')}")
    for i, x in enumerate(core.get("explorable", [])):
        if x.get("type") not in ("parametric", "definition_driven"):
            errors.append(f"explorable[{i}] type 非法或缺失: {x.get('type')}")
        if "algorithm_ref" not in x:
            errors.append(f"explorable[{i}] 缺少 algorithm_ref")
    return errors


def machine_checks(core):
    """把每个 case 交给校验引擎重算，返回逐条结果。"""
    results = []
    cases = list(core.get("cases", [])) + list(core.get("cases_practice", []))
    for c in cases:
        status, detail = check_case(c)
        results.append({
            "case_id": c.get("id"),
            "source_ref": c.get("source_ref"),
            "status": status,
            "detail": detail,
        })
    return results


def compare_with_baseline(core, baseline):
    def _set(items, key):
        return {_norm(x[key]) for x in items if key in x}

    b_terms = _set(baseline.get("dictionary", []), "term")
    c_terms = _set(core.get("dictionary", []), "term")
    b_cases, c_cases = _case_pool(baseline), _case_pool(core)

    # 算法按 source_ref 的"引用编号核心"匹配（书内编号体系比命名稳定：两条提取对
    # "结论5.7"的说法可以完全不同；"式(5.25)及后续讨论"与"式(5.25)"也应算同一条）。
    # 无编号核心时退化用 ref/名称的宽松归一化。展示时附上原命名，方便人工对照。
    def _cite_core(s):
        m = re.search(r"(结论|定义|式|定理|例|注)\s*\(?\s*(\d+)\.(\d+)", str(s))
        return f"{m.group(1)}{m.group(2)}.{m.group(3)}" if m else None

    def _algo_map(core_):
        m = {}
        for a in core_.get("algorithms", []):
            ref = a.get("source_ref") or ""
            key = _cite_core(ref) or _norm_ref(ref) or _norm(a.get("name", ""))
            if key:
                m[key] = a.get("name", key)
        return m

    b_algos, c_algos = _algo_map(baseline), _algo_map(core)

    def _cmp(b, c):
        hit = b & c
        return {
            "baseline": len(b), "found": len(hit),
            "recall": round(len(hit) / len(b), 3) if b else None,
            "missing": sorted(b - c), "extra": sorted(c - b),
        }

    algo_cmp = _cmp(set(b_algos), set(c_algos))
    algo_cmp["missing"] = [f"{k}（{b_algos[k]}）" for k in algo_cmp["missing"]]
    algo_cmp["extra"] = [f"{k}（{c_algos[k]}）" for k in algo_cmp["extra"]]

    return {
        "dictionary": _cmp(b_terms, c_terms),
        "algorithms": algo_cmp,
        "cases": _cmp(set(b_cases), set(c_cases)),
    }


def _num_core(s):
    """取引用里的编号数字核心（"定义3.31"/"3.31 后续讨论" -> "3.31"）。"""
    m = re.search(r"(\d+)\.(\d+)", str(s))
    return f"{m.group(1)}.{m.group(2)}" if m else None


def inventory_coverage(core, inventory):
    """对清点阶段的编号条目算总落地率。

    动机：人工基线只收了少数核心条目（3A-3C 仅 4 条算法），按基线算召回噪声很大；
    清单是同一模型对本节"有什么"的完整清点，用它当覆盖标尺公平得多。
    返回 None 表示没有清单（非两段式运行）。"""
    if not inventory:
        return None
    items = (inventory.get("definitions", []) + inventory.get("conclusions", [])
             + inventory.get("formulas", []))
    inv = {_num_core(x) for x in items}
    inv.discard(None)
    if not inv:
        return None
    col = {"algorithms": set(), "dictionary": set(), "cases": set()}
    for a in core.get("algorithms", []):
        col["algorithms"].add(_num_core(a.get("source_ref")))
    for d in core.get("dictionary", []):
        col["dictionary"].add(_num_core(d.get("source_ref")))
    for c in core.get("cases", []) + core.get("cases_practice", []):
        col["cases"].add(_num_core(c.get("source_ref")))
    landed = set()
    for s in col.values():
        landed |= s
    landed.discard(None)
    return {"items": len(inv), "landed": len(inv & landed),
            "rate": round(len(inv & landed) / len(inv), 3),
            "missing": sorted(inv - landed)}


def build_scorecard(core, baseline=None, inventory=None):
    schema_errors = validate_schema(core)
    checks = machine_checks(core)
    count = lambda s: sum(1 for r in checks if r["status"] == s)  # noqa: E731
    comparison = compare_with_baseline(core, baseline) if baseline else None
    return {
        "schema_valid": not schema_errors,
        "schema_errors": schema_errors,
        "machine_checks": {
            "pass": count("PASS"), "fail": count("FAIL"),
            "error": count("ERROR"), "skip": count("SKIP"),
            "detail": checks,
        },
        "baseline_comparison": comparison,
        "inventory_coverage": inventory_coverage(core, inventory),
        "human_spotcheck_needed": bool(comparison and (
            comparison["dictionary"]["extra"] or comparison["algorithms"]["extra"]
            or comparison["cases"]["extra"])),
        "gate_pass": not schema_errors and count("FAIL") == 0 and count("ERROR") == 0,
    }


def to_markdown(scorecard, run_meta=None):
    lines = ["# Harness 评测报告", ""]
    if run_meta:
        lines.append(f"- 运行信息: `{json.dumps(run_meta, ensure_ascii=False)}`")
    lines += [
        f"- 门槛(gate): {'PASS ✓' if scorecard['gate_pass'] else 'FAIL ✗'}"
        "（标准：schema 无错误，且机器验证无 FAIL/ERROR）",
        "",
        "## Schema 完整性",
        "- 通过" if scorecard["schema_valid"] else "- 存在问题：",
    ]
    lines += [f"  - {e}" for e in scorecard["schema_errors"]]
    mc = scorecard["machine_checks"]
    lines += [
        "",
        "## 机器验证（verify 声明重算）",
        f"- PASS {mc['pass']} / FAIL {mc['fail']} / ERROR {mc['error']} / SKIP {mc['skip']}",
    ]
    lines += [f"  - [{r['status']}] {r.get('case_id')} ({r.get('source_ref')}) — {r['detail']}"
              for r in mc["detail"]]
    cmp_ = scorecard.get("baseline_comparison")
    if cmp_:
        lines += ["", "## 基线对比（召回率为参考指标，基线自身也可能不全）"]
        for key in ("dictionary", "algorithms", "cases"):
            c = cmp_[key]
            rec = "n/a" if c["recall"] is None else format(c["recall"], ".0%")
            lines.append(f"- {key}: 基线 {c['baseline']} 项，命中 {c['found']}，召回 {rec}")
            if c["missing"]:
                lines.append(f"  - 缺失: {c['missing']}")
            if c["extra"]:
                lines.append(f"  - 基线外新增（需人工抽查：忠实还是幻觉）: {c['extra']}")
        lines.append(f"- 需人工抽查: {'是' if scorecard['human_spotcheck_needed'] else '否'}")
    ic = scorecard.get("inventory_coverage")
    if ic:
        lines += ["", "## 清单落地率（对本节编号条目清单的覆盖，比薄基线召回更公平）",
                  f"- {ic['landed']}/{ic['items']} = {format(ic['rate'], '.0%')}"]
        if ic["missing"]:
            lines.append(f"- 未落地编号: {ic['missing']}")
    return "\n".join(lines) + "\n"
