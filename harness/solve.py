"""生成-检验阶段：对 practice 案例提议候选答案并用注册表机器检验。

动机：证明型章节（如 LADR 6A）的"例"都是定义性的，机器验证无抓手；但不少习题
有唯一的数值/对象答案。让模型提议答案、注册表机器检验：
- PASS 的答案作为 candidate_answer 附在案例上（answer_verified=true）——
  为"检查我的答案"类产品功能提供可信底座；
- FAIL/ERROR 的提议直接丢弃（宁缺毋滥，错误答案绝不下发）。
"""
from prompts import build_solve_messages
from run_validation import check_case


def solve_practice(harness, core, section_meta):
    """对 core 的 cases_practice 生成候选答案并机器检验。返回 (core, stats)。"""
    # practice 案例可能出现在两处：旧布局的 cases_practice 或 schema v1 的 cases(role=practice)
    practice = [c for c in core.get("cases_practice", []) if not c.get("verify")]
    practice += [c for c in core.get("cases", [])
                 if c.get("role") == "practice" and not c.get("verify")]
    stats = {"practice": len(practice), "proposed": 0, "verified": 0}
    if not practice:
        return core, stats

    by_id = {c.get("id"): c for c in practice}
    try:
        out = harness.complete_json(build_solve_messages(section_meta, practice))
    except Exception as e:  # 求解阶段失败不影响主提取结果
        stats["error"] = str(e)[:200]
        return core, stats

    for s in (out.get("solved", []) if isinstance(out, dict) else []):
        case = by_id.get(s.get("case_id"))
        if not case or not isinstance(s.get("verify"), dict):
            continue
        stats["proposed"] += 1
        status, detail = check_case({"verify": s["verify"]})
        if status == "PASS":
            case["candidate_answer"] = str(s.get("answer", ""))[:300]
            case["verify"] = s["verify"]
            case["answer_verified"] = True
            stats["verified"] += 1
        else:  # 完整提议留档，便于区分"答错"与"答案对但声明写错"
            stats.setdefault("rejected", []).append({
                "case_id": s.get("case_id"), "status": status,
                "function": s["verify"].get("function"),
                "answer": str(s.get("answer", ""))[:300],
                "verify": s["verify"], "detail": detail[:150],
            })
    return core, stats
