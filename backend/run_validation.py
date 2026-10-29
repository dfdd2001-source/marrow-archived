"""
Marrow 通用case校验运行器
用法: python3 run_validation.py <core_json_path> [<core_json_path> ...]
"""
import json
import sys
from validation.verifiers import REGISTRY


def _close(a, b):
    """判等：精确相等优先；涉及浮点时按相对容差 1e-9 判等。
    动机：0.3 - 0.1*3 = -5.5e-17 这类 IEEE 浮点噪声会把正确的答案误判为 FAIL。
    递归支持矩阵/向量（list/tuple），bool 不做数值化。"""
    if isinstance(a, bool) or isinstance(b, bool):
        # bool 不做数值化：True 与 1 在 Python 里 == 为真，但语义上 bool 只与 bool 判等
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    if fa == fb:
        return True
    return abs(fa - fb) <= 1e-9 * max(1.0, abs(fb))


def check_case(case):
    verify = case.get("verify")
    if not verify:
        note = case.get("verify_note", "未声明verify，跳过")
        return "SKIP", note
    if not isinstance(verify, dict) or not isinstance(verify.get("args"), dict) \
            or not isinstance(verify.get("function"), str):
        return "ERROR", ("verify 格式错误：应为 {function: 函数名, args: {参数字典}, "
                         "expected|expected_equal|expected_zero_vector}")

    # 防御性归一：模型常把期望值错写进 args，自动提升到 verify 顶层（不改原 case）
    args = verify.get("args") or {}
    verify = dict(verify)
    for k in ("expected", "expected_equal", "expected_zero_vector"):
        if k not in verify and k in args:
            verify[k] = args[k]

    fn_name = verify["function"]
    if fn_name not in REGISTRY:
        return "ERROR", f"未注册的校验函数: {fn_name}"

    fn = REGISTRY[fn_name]
    # expected/expected_equal/expected_zero_vector 是引擎保留的比较键，
    # 不属于任何校验函数的入参——剥离后再调用（模型错位写法因此无缝工作）
    call_args = {k: v for k, v in verify["args"].items()
                 if k not in ("expected", "expected_equal", "expected_zero_vector")}
    try:
        result = fn(**call_args)
    except TypeError as e:
        # 模型常套用其他函数的参数名（如给 adjoint_matrix 传 T_coeffs）——报出正确签名而非崩溃
        import inspect
        return "ERROR", f"参数不匹配，{fn_name} 的签名应为 {fn_name}{inspect.signature(fn)}: {e}"
    except ValueError as e:
        # 求解类函数的业务性失败（如对奇异矩阵解线性方程组）——报出原因而非崩溃
        return "ERROR", f"{fn_name}: {e}"

    if "expected" in verify:
        ok = _close(result, verify["expected"])
        return ("PASS" if ok else "FAIL"), f"算得 {result}，期望 {verify['expected']}"

    if "expected_equal" in verify:
        # expected_equal 只适用于返回 (Tv, lam_v, is_equal) 三元组的 eigenvector_check；
        # 盲测曾把它误声明在返回矩阵的函数上——明确报错而非崩溃
        if not (isinstance(result, tuple) and len(result) == 3 and isinstance(result[2], bool)):
            return "ERROR", (f"expected_equal 只适用于 eigenvector_check（返回三元组），"
                             f"{fn_name} 返回 {type(result).__name__}")
        Tv, lam_v, is_equal = result
        ok = is_equal == verify["expected_equal"]
        return ("PASS" if ok else "FAIL"), f"Tv={Tv}, λv={lam_v}, 相等={is_equal}"

    if "expected_zero_vector" in verify:
        ok = all(_close(x, 0) for x in result) == verify["expected_zero_vector"]
        return ("PASS" if ok else "FAIL"), f"残差={result}"

    return "ERROR", "verify声明里没有可识别的期望值字段"


def validate_core(path):
    with open(path, "r", encoding="utf-8") as f:
        core = json.load(f)

    print(f"\n=== {core['topic']} ({path}) ===")
    all_cases = core.get("cases", [])
    results = []
    for case in all_cases:
        status, detail = check_case(case)
        results.append(status)
        print(f"  [{status}] {case['id']} ({case.get('source_ref','?')}) — {detail}")

    n_pass = results.count("PASS")
    n_fail = results.count("FAIL")
    n_skip = results.count("SKIP")
    n_error = results.count("ERROR")
    print(f"  合计: {n_pass} PASS / {n_fail} FAIL / {n_skip} SKIP / {n_error} ERROR")
    return n_fail == 0 and n_error == 0


if __name__ == "__main__":
    paths = sys.argv[1:]
    all_ok = True
    for p in paths:
        ok = validate_core(p)
        all_ok = all_ok and ok
    print("\n" + ("全部通过 ✓" if all_ok else "存在未通过项 ✗"))
