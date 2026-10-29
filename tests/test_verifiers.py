"""校验引擎注册表的单元测试：backend/validation/verifiers.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from validation.verifiers import (  # noqa: E402
    REGISTRY,
    adjoint_matrix,
    determinant,
    dot_product,
    eigenvector_check,
    matrix_of_linear_map,
    matrix_product,
    minimal_poly_residual,
    polynomial_derivative_matrix,
    solve_linear,
    vector_norm,
)


class RegistryTest(unittest.TestCase):
    def test_all_functions_registered(self):
        for name in ("matrix_of_linear_map", "polynomial_derivative_matrix",
                     "eigenvector_check", "minimal_poly_residual", "dot_product",
                     "vector_norm", "adjoint_matrix", "matrix_product"):
            self.assertIn(name, REGISTRY)


class MatrixOfLinearMapTest(unittest.TestCase):
    def test_column_convention(self):
        # T(x,y)=(2x+y, 3y)：M(T) 第 k 列 = T(e_k) → [[2,1],[0,3]]
        self.assertEqual(matrix_of_linear_map([[2, 1], [0, 3]], 2), [[2, 1], [0, 3]])

    def test_rectangular_shape(self):
        # R²→R³：T(x,y)=(x, x+y, 2y)，输出 3 行 2 列
        M = matrix_of_linear_map([[1, 0], [1, 1], [0, 2]], 2)
        self.assertEqual(len(M), 3)
        self.assertEqual([len(r) for r in M], [2, 2, 2])
        self.assertEqual(M, [[1, 0], [1, 1], [0, 2]])


class PolynomialDerivativeMatrixTest(unittest.TestCase):
    def test_d_on_p3(self):
        # P3→P3：d/dx 把 x^k 变成 k·x^(k-1)，维数 4（最高次系数行为全零行）
        self.assertEqual(polynomial_derivative_matrix(3, 3),
                         [[0, 1, 0, 0], [0, 0, 2, 0], [0, 0, 0, 3], [0, 0, 0, 0]])

    def test_codomain_smaller(self):
        # P3→P2：x³ 的导数 x² 保留，常数项维数裁剪
        self.assertEqual(polynomial_derivative_matrix(3, 2),
                         [[0, 1, 0, 0], [0, 0, 2, 0], [0, 0, 0, 3]])


class EigenvectorCheckTest(unittest.TestCase):
    T = [[3, 1], [0, 4]]  # 特征值 4、3；(1,1) 是 λ=4 的特征向量

    def test_positive(self):
        Tv, lam_v, is_equal = eigenvector_check(self.T, [1, 1], 4)
        self.assertEqual(Tv, [4, 4])
        self.assertEqual(lam_v, [4, 4])
        self.assertTrue(is_equal)

    def test_wrong_lambda(self):
        _, _, is_equal = eigenvector_check(self.T, [1, 1], 3)
        self.assertFalse(is_equal)

    def test_zero_vector_is_not_eigenvector(self):
        # 定义要求 v≠0：零向量必须判否，否则 Tv=λv=0 平凡成立（盲测曾借此漏过负验证）
        _, _, is_equal = eigenvector_check(self.T, [0, 0], 4)
        self.assertFalse(is_equal)


class MinimalPolyResidualTest(unittest.TestCase):
    T = [[3, 1], [0, 4]]  # 特征多项式 z²-7z+12 → coeffs=[12, -7]

    def test_residual_zero_for_char_poly(self):
        self.assertEqual(minimal_poly_residual(self.T, [1, 1], [12, -7], 2), [0, 0])

    def test_residual_nonzero_for_wrong_coeffs(self):
        self.assertNotEqual(minimal_poly_residual(self.T, [1, 1], [0, 0], 2), [0, 0])


class InnerProductTest(unittest.TestCase):
    def test_dot_product(self):
        self.assertEqual(dot_product([1, 2, 3], [4, 5, 6]), 32)

    def test_orthogonal(self):
        self.assertEqual(dot_product([1, 0], [0, 1]), 0)

    def test_norm(self):
        self.assertEqual(vector_norm([3, 4]), 5.0)


class AdjointMatrixTest(unittest.TestCase):
    def test_real_is_transpose(self):
        self.assertEqual(adjoint_matrix([[0, 1, 3], [2, 0, 0]]),
                         [[0, 2], [1, 0], [3, 0]])

    def test_complex_conjugate_transpose(self):
        # 复数条目 a+bi 编码为 [a, b]，共轭后虚部变号
        self.assertEqual(adjoint_matrix([[[1, 2]]]), [[[1, -2]]])


class DeterminantTest(unittest.TestCase):
    def test_2x2_int(self):
        self.assertEqual(determinant([[2, 1], [1, 2]]), 3)

    def test_3x3_int(self):
        self.assertEqual(determinant([[1, 2, 3], [4, 5, 6], [7, 8, 10]]), -3)

    def test_singular_is_zero(self):
        self.assertEqual(determinant([[1, 2], [2, 4]]), 0)

    def test_complex_entries_encoded(self):
        # [[1+2i, i],[3, 1+i]] 的行列式 = -1（复数条目 [a,b] 编码）
        self.assertEqual(determinant([[[1, 2], [0, 1]], [[3, 0], [1, 1]]]), [-1, 0])


class SolveLinearTest(unittest.TestCase):
    def test_unique_solution(self):
        # 2x+y=5, x+3y=10 → x=1, y=3
        self.assertEqual(solve_linear([[2, 1], [1, 3]], [5, 10]), [1.0, 3.0])

    def test_singular_raises(self):
        with self.assertRaises(ValueError):
            solve_linear([[1, 2], [2, 4]], [1, 2])


class MatrixProductTest(unittest.TestCase):
    def test_known_product(self):
        self.assertEqual(matrix_product([[1, 2], [3, 4]], [[5, 6], [7, 8]]),
                         [[19, 22], [43, 50]])


if __name__ == "__main__":
    unittest.main()
