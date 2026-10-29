"""check_case 判定语义的单元测试：backend/run_validation.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from run_validation import _close, check_case  # noqa: E402


class CloseTest(unittest.TestCase):
    def test_float_noise_tolerated(self):
        # 动机用例：0.1*3 与 0.3 的 IEEE 噪声不误杀
        self.assertTrue(_close(0.1 + 0.2, 0.3))

    def test_real_difference_rejected(self):
        self.assertFalse(_close(1.0, 1.1))

    def test_recursive_vectors(self):
        self.assertTrue(_close([1, [2, 3]], [1.0, [2.0, 3.0]]))

    def test_bool_not_numeric(self):
        self.assertFalse(_close(True, 1))

    def test_non_numeric_exact(self):
        self.assertTrue(_close("abc", "abc"))
        self.assertFalse(_close("abc", "abd"))


class CheckCaseStatusTest(unittest.TestCase):
    def test_no_verify_skips(self):
        status, _ = check_case({"id": "c"})
        self.assertEqual(status, "SKIP")

    def test_bad_format_errors(self):
        status, _ = check_case({"id": "c", "verify": "dot_product"})
        self.assertEqual(status, "ERROR")

    def test_unknown_function_errors(self):
        status, detail = check_case({"id": "c", "verify": {
            "function": "no_such_fn", "args": {"u": [1]}, "expected": 1}})
        self.assertEqual(status, "ERROR")
        self.assertIn("no_such_fn", detail)

    def test_param_mismatch_reports_signature(self):
        # 给 dot_product 传矩阵函数的参数名——报签名而非崩溃
        status, detail = check_case({"id": "c", "verify": {
            "function": "dot_product", "args": {"T_coeffs": [[1]], "domain_dim": 1}, "expected": 1}})
        self.assertEqual(status, "ERROR")
        self.assertIn("dot_product", detail)
        self.assertIn("u", detail)


class ExpectedComparisonTest(unittest.TestCase):
    def test_pass(self):
        status, _ = check_case({"id": "c", "verify": {
            "function": "dot_product", "args": {"u": [1, 2, 3], "v": [4, 5, 6]}, "expected": 32}})
        self.assertEqual(status, "PASS")

    def test_float_noise_pass(self):
        status, _ = check_case({"id": "c", "verify": {
            "function": "dot_product", "args": {"u": [0.1, 0.2], "v": [1, 1]}, "expected": 0.3}})
        self.assertEqual(status, "PASS")

    def test_fail(self):
        status, _ = check_case({"id": "c", "verify": {
            "function": "dot_product", "args": {"u": [1], "v": [1]}, "expected": 999}})
        self.assertEqual(status, "FAIL")

    def test_expected_misplaced_in_args_is_promoted(self):
        # 模型常把期望值错写进 args——防御性归一后应无缝工作
        status, _ = check_case({"id": "c", "verify": {
            "function": "dot_product", "args": {"u": [1, 2], "v": [3, 4], "expected": 11}}})
        self.assertEqual(status, "PASS")


class SolverBusinessErrorsTest(unittest.TestCase):
    def test_singular_matrix_reports_not_crashes(self):
        # solve_linear 对奇异矩阵抛 ValueError——check_case 应转为 ERROR 而非向上传播
        status, detail = check_case({"id": "c", "verify": {
            "function": "solve_linear", "args": {"M": [[1, 2], [2, 4]], "b": [1, 2]},
            "expected": [0, 0]}})
        self.assertEqual(status, "ERROR")
        self.assertIn("奇异", detail)


class ExpectedEqualTest(unittest.TestCase):
    def test_pass(self):
        status, _ = check_case({"id": "c", "verify": {
            "function": "eigenvector_check",
            "args": {"T_coeffs": [[3, 1], [0, 4]], "v": [1, 1], "lam": 4},
            "expected_equal": True}})
        self.assertEqual(status, "PASS")

    def test_negative_verification(self):
        # 负验证同样合法：判定某向量不是特征向量
        status, _ = check_case({"id": "c", "verify": {
            "function": "eigenvector_check",
            "args": {"T_coeffs": [[3, 1], [0, 4]], "v": [1, 1], "lam": 3},
            "expected_equal": False}})
        self.assertEqual(status, "PASS")

    def test_only_valid_for_triple_return(self):
        # expected_equal 误用在返回矩阵的函数上——明确报错而非崩溃
        status, _ = check_case({"id": "c", "verify": {
            "function": "dot_product", "args": {"u": [1], "v": [1]}, "expected_equal": True}})
        self.assertEqual(status, "ERROR")


class ExpectedZeroVectorTest(unittest.TestCase):
    def test_pass(self):
        status, _ = check_case({"id": "c", "verify": {
            "function": "minimal_poly_residual",
            "args": {"T_coeffs": [[3, 1], [0, 4]], "v": [1, 1], "coeffs": [12, -7],
                     "target_degree": 2},
            "expected_zero_vector": True}})
        self.assertEqual(status, "PASS")

    def test_negative_verification(self):
        # 残差非零 + expected_zero_vector=false → PASS（负验证）
        status, _ = check_case({"id": "c", "verify": {
            "function": "minimal_poly_residual",
            "args": {"T_coeffs": [[3, 1], [0, 4]], "v": [1, 1], "coeffs": [0, 0],
                     "target_degree": 2},
            "expected_zero_vector": False}})
        self.assertEqual(status, "PASS")


if __name__ == "__main__":
    unittest.main()
