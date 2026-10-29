"""Marrow harness 提取 prompt。

盲测保证：这里只有 schema、校验机制说明和提取规则，绝不包含 cores/ 下
任何人工基线内容。基线只在评测阶段(evaluate.py)出现，prompt 里没有。
"""

REGISTRY_SPEC = """1. matrix_of_linear_map(T_coeffs, domain_dim) -> M(T)
   求线性映射关于标准基的矩阵。T_coeffs[i][j] = 输出第 i 个分量里 x_j 的系数；返回 m×n 矩阵（行=输出分量，列=定义域基）。
2. polynomial_derivative_matrix(domain_degree, codomain_degree) -> M(D)
   多项式求导映射 Dp=p' 在标准基下的矩阵。两个参数是定义域/值域多项式的次数上限。
3. eigenvector_check(T_coeffs, v, lam) -> (Tv, lam_v, is_equal)
   判定非零向量 v 是否为 T 关于 λ 的特征向量（Tv 与 λv 是否相等）。T_coeffs 为方阵系数，含义同上。
4. minimal_poly_residual(T_coeffs, v, coeffs, target_degree) -> 残差向量
   验证最小多项式候选：p(z) = c0 + c1*z + ... + c_{n-1}*z^(n-1) + z^n，coeffs=[c0,...,c_{n-1}]，
   v 为取定的非零向量，target_degree = n。残差 = c0*v + c1*Tv + ... + T^n*v，正确时应为零向量。
5. dot_product(u, v) -> 内积值
   计算标准点积 ⟨u,v⟩ = Σ u_i·v_i，与 verify 顶层的 expected 比较（浮点有容差，噪声不误杀）。
6. vector_norm(v) -> 范数值
   计算 ∥v∥ = √(Σ v_i²)。浮点场景优先考虑能否改用 dot_product 对 ⟨v,v⟩ 做整数级验证。
7. adjoint_matrix(M) -> 共轭转置（定义7.1 伴随的矩阵实现）
   实矩阵即转置：adjoint_matrix([[0,1,3],[2,0,0]]) 得 [[0,2],[1,0],[3,0]]。
   复数条目 a+bi 统一写成 [a,b]，共轭后虚部变号：adjoint_matrix([[[1,2]]]) 得 [[[1,-2]]]。
   整个矩阵所有条目统一编码，expected 也按同编码逐条写出。
   验证"某算子的伴随矩阵"必须用本函数（传 M(T)），不要用 matrix_of_linear_map——
   那只会算出 M(T) 本身而不是 M(T*)。示意（虚构数据）：T(x,y)=(2x+y,3y) 的 M(T)=[[2,1],[0,3]]，
   M(T*)=[[2,0],[1,3]]，verify={"function":"adjoint_matrix","args":{"M":[[2,1],[0,3]]},"expected":[[2,0],[1,3]]}。
   也可以退一步用 matrix_of_linear_map 验证 M(T*)：此时 args 的 T_coeffs 必须填 T* 自己的系数。
8. matrix_product(A, B) -> 实矩阵乘积 A·B
   仅支持实条目。
9. determinant(M) -> n×n 行列式（9C 行列式的直接实现）
   整数矩阵返回精确整数；复数条目 a+bi 写成 [a,b]，返回值同样编码。
10. solve_linear(M, b) -> 解 M·x = b，返回解向量 [x1,...,xn]（2A/2B：线性组合系数/基坐标）
   M 为 n×n 方阵；矩阵奇异（组线性相关、无唯一分解）时报错——此时不要用本函数，
   改用 determinant 声明"不可分解"类验证。"""

SYSTEM_PROMPT = """你是一个严格的技术书籍知识提取引擎。任务：把给定章节原文，提取成一份符合给定 JSON schema 的 core 数据。

## 硬性规则
- 输出必须是单个 JSON 对象，不要输出任何解释、前后缀或 markdown 代码块。
- 只依据给定原文提取。禁止用通用教材知识补全原文没有出现的定义、结论或例题。
- source_ref 必须精确到原文编号（如"定义3.31"、"结论5.7"、"式(5.25)"），不能只写章节号，
  不能写页码或"后续讨论"之类的模糊指代。
- 覆盖完整性：本节出现的每一个编号结论/定义（"结论X.Y""定义X.Y"）都必须落在提取结果里——
  可操作结论/判据/构造规则进 algorithms，术语概念进 dictionary。本节的全部习题也必须逐题收进
  cases（role="practice"），不许省略或只挑几个。核心结论或习题有遗漏即为缺陷。

## 各字段要求
- topic: 本 core 覆盖的主题，收窄到节级。
- source: {book, section, page_range}，按输入给的章节信息填写。
- status: 固定填 "extracted_unverified"（你无权自评 verified，verified 由人工审核授予）。
- dictionary: 章节引入的全部术语，每条含 term / definition / source_ref。
- structure: nodes + edges，每条 edge 含 from / to / relation，relation 要写清具体依赖（如"3.15 建立在定义3.11之上"），不能只写"相关"。
- algorithms: 章节给出的可操作结论/构造规则，每条含 id / name / statement / source_ref / executable。
  executable=true 仅当 statement 精确到可以直接写成代码。
- cases: 原文中的全部"例"和"习题"，每条含 id / content / source_ref / role / is_verbatim：
  - role="validation"：原文直接给出解或数值结果的"例"；
  - role="practice"：原文不给答案的"习题"（这类不能冒充 validation）；
  - is_verbatim=true 仅当期望结果是原文直接给出的数值/结论，而非你推算的。
- explorable: 有算法适合做成可交互探索时给出，每项含 type / algorithm_ref，以及：
  - type="parametric"：连续参数可调，配 parameters（id / range / default）和 outputs；
  - type="definition_driven"：按定义分步构造，配 steps（分步文案）和 outputs；
  - outputs 每条含 label / expr，expr 是用参数 id 作变量的可求值 JS 表达式
    （支持数字、四则运算、数组与嵌套数组字面量，如 "[a*x+b*y, c*x+d*y]"）。
- related_cores: 原文明确依赖其他章节内容时给出 core_id + via（说明具体关联），core_id 从
  __RELATED_CORE_IDS__ 中选；没有明确关联就给空数组。

## verify 声明（机器验证机制）
**硬性要求：每一个 role="validation" 的案例必须满足其一，不许两者皆无：**
1. 带可用注册函数表达的 verify 声明（优先——凡含数值计算的案例：矩阵、向量、多项式系数、
   方程求解，都必须 verify 而不是靠 verify_note 推脱）；
2. 带 verify_note 说明为何无法用注册函数验证。

负验证同样合法：判定"不满足某性质"也可声明（如 expected_equal=false 验证某向量不是特征向量）。

格式示例（内容为虚构演示，与本任务无关，仅示意写法）：
{"id":"demo1", "content":"T(x,y)=(3x+y,4y)，验证 (1,1) 是 λ=4 的特征向量", "source_ref":"例X.Y",
 "role":"validation", "is_verbatim":true,
 "verify":{"function":"eigenvector_check","args":{"T_coeffs":[[3,1],[0,4]],"v":[1,1],"lam":4},"expected_equal":true}}

verify 里的期望字段三选一：
- "expected": 与函数返回值精确相等（适用于返回矩阵/数值的函数，直接写 JSON 矩阵字面量）
- "expected_equal": 布尔值，适用于返回 (Tv, lam_v, is_equal) 三元组的 eigenvector_check
- "expected_zero_vector": 布尔值，适用于返回残差向量的 minimal_poly_residual，true 表示残差应为零向量

可用注册函数：
__REGISTRY_SPEC__

无法用注册函数验证的 validation 案例，加 "verify_note": "无对应注册函数，需人工核对"。
practice 案例不需要 verify。"""


def build_messages(source_text, section_meta, schema_json, related_core_ids=None,
                   coverage_checklist=None):
    ids = ", ".join(related_core_ids) if related_core_ids else "（无，给空数组）"
    system = (SYSTEM_PROMPT
              .replace("__REGISTRY_SPEC__", REGISTRY_SPEC)
              .replace("__RELATED_CORE_IDS__", ids))
    user = (
        "## 章节信息\n"
        f"book: {section_meta['book']}\n"
        f"section: {section_meta['section']}\n"
        f"page_range: {section_meta.get('page_range') or '未提供'}\n\n"
        "## core JSON schema\n"
        f"{schema_json}\n\n"
        "## 章节原文\n"
        f"{source_text}"
    )
    if coverage_checklist:
        user += (
            "\n\n## 覆盖检查清单（第一段清点结果，第二段提取必须逐条落实，一个不许漏）\n"
            "对应关系：**可操作的规则/判据/构造步骤 → algorithms（哪怕编号叫'定义'，"
            "如矩阵构造规则这类可执行的都算）**；纯术语概念 → dictionary；"
            "例 → cases(role=validation)；习题 → cases(role=practice)。\n"
            f"{coverage_checklist}"
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


INVENTORY_SYSTEM = """你是一个严格的技术书籍结构清点引擎。任务：通读给定章节原文，清点其中出现的**每一个编号条目**，不做任何提取或展开。

输出单个 JSON 对象，四个键都必须存在（可为空数组）：
{"definitions": ["定义X.Y：一句话主题", ...],
 "conclusions": ["结论X.Y：一句话主题", ...],
 "formulas": ["式(X.Y)：一句话主题", ...],
 "examples": ["例X.Y：一句话主题", ...],
 "exercises": ["习题X.Y", ...]}

规则：
- 只依据给定原文；编号必须逐字照抄原文（含括号后缀如"结论5.27(a)"）。
- 完整性是本任务的全部意义：正文和文末习题列表里的每个编号条目都要出现，一个不许漏。
- 习题只列编号，不抄题目内容。
- 不要输出任何解释或 markdown 代码块。"""


def build_inventory_messages(source_text, section_meta):
    user = (
        "## 章节信息\n"
        f"book: {section_meta['book']}\n"
        f"section: {section_meta['section']}\n"
        f"page_range: {section_meta.get('page_range') or '未提供'}\n\n"
        "## 章节原文\n"
        f"{source_text}"
    )
    return [
        {"role": "system", "content": INVENTORY_SYSTEM},
        {"role": "user", "content": user},
    ]


SOLVE_SYSTEM = """你是严格的技术习题求解器。给定习题清单，只对**能给出具体可检验答案**的习题
（数值、向量、矩阵等具体对象）逐题求解，并声明机器验证；纯证明题没有可计算答案，直接跳过。

规则：
- 只依据习题内容求解，不引入原文没有的假设。
- 证明题没有可计算答案，**禁止用一个满足题设的实例冒充证明**。如果你提供的只是
  满足题设的具体实例（witness），answer 必须以"实例验证："开头注明，且实例必须
  真正满足题目的全部条件——机器会逐条检验，任何一条不满足都会被拒绝。
- verify 声明格式与期望字段：
  {"function": 函数名, "args": {...}, "expected"|"expected_equal"|"expected_zero_vector"}
  一个 verify 只能声明一个检验；答案含多个条件时，挑最核心的可检验条件。

可用注册函数：
__REGISTRY_SPEC__

输出单个 JSON 对象：{"solved": [{"case_id": "习题案例id", "answer": "答案表述", "verify": {...}}]}
没有可求解的习题就输出 {"solved": []}。不要输出解释或 markdown 代码块。"""


def build_solve_messages(section_meta, practice_cases):
    listing = "\n".join(
        f"- id={c.get('id')} | {c.get('source_ref', '')} | {c.get('content', '')[:150]}"
        for c in practice_cases)
    system = SOLVE_SYSTEM.replace("__REGISTRY_SPEC__", REGISTRY_SPEC)
    user = (
        f"## 章节信息\n"
        f"book: {section_meta['book']}\n"
        f"section: {section_meta['section']}\n\n"
        f"## 可尝试求解的习题\n{listing}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
