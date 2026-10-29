"""
Marrow 校验引擎 —— 算法实现库

设计原则：每个函数对应schema里algorithms[].id能引用到的一种"算法形状"。
case不再需要临时代码，只需要在cases[].verify里声明用哪个函数、传什么参数。
新算法形状出现时，往这里加一个函数、注册一下，就是全部要做的事——
不是"永远不用写代码"，是"同一种算法形状只写一次代码"。
"""

def matrix_of_linear_map(T_coeffs, domain_dim):
    """
    matrix_construction 算法（定义3.31）
    T_coeffs: 关于标准基的系数矩阵，T_coeffs[i][j] 表示输出第i个分量里 x_j 的系数
    domain_dim: 定义域维数
    返回: M(T)，按列构造 —— 第k列 = T(e_k)
    """
    codomain_dim = len(T_coeffs)
    columns = []
    for k in range(domain_dim):
        e_k = [1 if i == k else 0 for i in range(domain_dim)]
        col = [sum(T_coeffs[row][j] * e_k[j] for j in range(domain_dim)) for row in range(codomain_dim)]
        columns.append(col)
    # 转成行优先的矩阵
    return [[columns[c][r] for c in range(domain_dim)] for r in range(codomain_dim)]


def polynomial_derivative_matrix(domain_degree, codomain_degree):
    """
    多项式求导映射的矩阵（例3.33同类问题）
    domain_degree: 定义域P_n(F)的n（次数上限，维数为n+1）
    codomain_degree: 值域P_m(F)的m
    标准基下，求导映射把 x^k 变成 k*x^(k-1)
    """
    domain_dim = domain_degree + 1
    codomain_dim = codomain_degree + 1
    M = [[0] * domain_dim for _ in range(codomain_dim)]
    for k in range(1, domain_dim):
        if k - 1 < codomain_dim:
            M[k - 1][k] = k
    return M


def eigenvector_check(T_coeffs, v, lam):
    """
    特征向量判定（定义5.8）：Tv == λv ?
    T_coeffs: T的系数矩阵（方阵，T_coeffs[i][j]是输出第i分量里x_j的系数）
    v: 候选特征向量
    lam: 候选特征值
    注意：零向量不是特征向量（定义要求 v≠0），必须排除——否则 Tv=λv=0 平凡成立，
    盲测曾借此让一个错误的负验证声明漏成"相等"。
    """
    n = len(v)
    Tv = [sum(T_coeffs[i][j] * v[j] for j in range(n)) for i in range(n)]
    lam_v = [lam * x for x in v]
    return Tv, lam_v, (Tv == lam_v and any(x != 0 for x in v))


def minimal_poly_residual(T_coeffs, v, coeffs, target_degree):
    """
    最小多项式的实用求法验证（式5.25）
    T_coeffs: T的系数矩阵
    v: 取定的向量
    coeffs: 候选系数 [c0, c1, ..., c_{n-1}]，多项式为 c0+c1*z+...+c_{n-1}*z^(n-1)+z^n
    target_degree: n
    返回残差向量：c0*v + c1*Tv + ... + c_{n-1}*T^(n-1)v + T^n*v，应为零向量
    """
    def apply_T(vec):
        return [sum(T_coeffs[i][j] * vec[j] for j in range(len(vec))) for i in range(len(T_coeffs))]

    n = len(v)
    residual = [0] * n
    current = v
    for c in coeffs:
        residual = [residual[i] + c * current[i] for i in range(n)]
        current = apply_T(current)
    # current现在是 T^(len(coeffs)) v，还差到T^target_degree v
    for _ in range(target_degree - len(coeffs)):
        current = apply_T(current)
    residual = [residual[i] + current[i] for i in range(n)]
    return residual


def dot_product(u, v):
    """
    标准点积/内积计算（定义6.1/6.3 同类问题，6A 新增形状）
    u, v: 等长向量。返回 ⟨u,v⟩，由 check_case 与 verify 顶层 expected 比较（浮点有 1e-9 容差）。
    """
    return sum(a * b for a, b in zip(u, v))


def vector_norm(v):
    """
    欧式范数计算（定义6.7 同类问题：∥v∥=√⟨v,v⟩，6A 新增形状）
    v: 向量。返回 ∥v∥，由 check_case 与 expected 比较。
    浮点场景优先考虑能否改用 dot_product 对 ⟨v,v⟩ 做整数级验证。
    """
    import math
    return math.sqrt(sum(x * x for x in v))


def adjoint_matrix(M):
    """
    共轭转置（定义7.1 伴随的矩阵实现，7A 新增形状）：返回 M 的共轭转置。
    实矩阵即转置。条目编码：实数为数字，复数 a+bi 写成 [a, b]；
    返回与输入同编码，由 check_case 与 verify 顶层 expected 比较（浮点有容差）。
    """
    def conj(x):
        if isinstance(x, list) and len(x) == 2:
            return [x[0], -x[1]]
        return x

    rows, cols = len(M), len(M[0])
    return [[conj(M[r][c]) for r in range(rows)] for c in range(cols)]


def matrix_product(A, B):
    """
    实矩阵乘法（7A 新增形状：如验证 T*T = TT* 的中间步骤）。
    仅支持实条目；复数场景请拆解为分量或用 adjoint_matrix 组合。
    """
    n, m, p = len(A), len(B), len(B[0])
    out = [[0] * p for _ in range(n)]
    for i in range(n):
        for j in range(p):
            out[i][j] = sum(A[i][k] * B[k][j] for k in range(m))
    return out


def determinant(M):
    """
    n×n 行列式（9C 新增形状）：按第一行拉普拉斯展开，O(n!)。
    整数矩阵得精确整数；条目实数为数字，复数 a+bi 写成 [a, b]（与 adjoint_matrix 同编码）。
    """
    total = _det_laplace(M)
    if isinstance(total, complex):
        return [total.real, total.imag]
    return total


def _det_laplace(M):
    def val(x):
        if isinstance(x, list) and len(x) == 2:
            return complex(x[0], x[1])
        return x

    n = len(M)
    if n == 1:
        return val(M[0][0])
    if n == 2:
        return val(M[0][0]) * val(M[1][1]) - val(M[0][1]) * val(M[1][0])
    total = 0
    for j in range(n):
        minor = [row[:j] + row[j + 1:] for row in M[1:]]
        term = val(M[0][j]) * _det_laplace(minor)
        total = total - term if j % 2 else total + term
    return total


def solve_linear(M, b):
    """
    解线性方程组 M·x = b（2A/2B 新增形状：把 v 写成给定组的线性组合、基坐标）。
    部分主元高斯消元；奇异矩阵抛 ValueError（调用方据 expected 的错误语义自行声明）。
    返回解向量 [x1, x2, ...]。
    """
    n = len(M)
    if any(len(row) != n for row in M) or len(b) != n:
        raise ValueError("M 必须是 n×n 方阵且 b 长度为 n")
    aug = [[float(M[i][j]) for j in range(n)] + [float(b[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("矩阵奇异（线性相关），无唯一解")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col] / aug[col][col]
            for c in range(col, n + 1):
                aug[r][c] -= factor * aug[col][c]
    return [aug[i][n] / aug[i][i] for i in range(n)]


REGISTRY = {
    "matrix_of_linear_map": matrix_of_linear_map,
    "polynomial_derivative_matrix": polynomial_derivative_matrix,
    "eigenvector_check": eigenvector_check,
    "minimal_poly_residual": minimal_poly_residual,
    "dot_product": dot_product,
    "vector_norm": vector_norm,
    "adjoint_matrix": adjoint_matrix,
    "matrix_product": matrix_product,
    "determinant": determinant,
    "solve_linear": solve_linear,
}
