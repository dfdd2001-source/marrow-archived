# Marrow

把任意一本技术/科普书籍 PDF，变成**可探索式交互学习工具**的 AI 流水线：

> 提取知识结构 → 建立可运行的数学模型 → 生成可探索的交互界面

打开任意一节：拖动向量与滑块，实时看定义与定理在几何里发生；做书里的每一道习题，
少数数值题带有**经过机器验证**的参考答案。PWA 离线可用。

**自带一个手写演示节**（`cores/demo-d1.json`，2×2 矩阵与线性变换，MIT 同样许可）——
克隆后 5 分钟内可跑通全流程；你的书用「导入书籍」流水线自己生成。

## 快速开始

```bash
git clone https://github.com/dfdd2001-source/marrow.git && cd marrow
./scripts/install_hooks.sh      # 可选：安装 pre-push 门禁
./scripts/serve_app.sh          # 纯静态模式：http://127.0.0.1:8765/（无需后端）
```

要导入你自己的书（需要 `pdftotext`、Python + FastAPI 环境与 AI 网关密钥）：

```bash
cp .env.example .env            # 填入 AGNES_API_KEY
./scripts/serve_platform.sh     # 平台模式：同地址，多出「导入书籍」与账号同步
```

导入流程：填 PDF 路径 → 启发式探测章节 → 人工勾选 → 流水线（每节 3-6 分钟）。
生成内容落在本机 `cores/`，**请自行遵守原书版权**。

## 它解决什么问题

手工做一份"可探索式讲解"极贵，Marrow 用 AI 流水线把它自动化，并用三件事保证质量：
- **盲测纪律**：提取 prompt 绝不含基线内容，召回对比只在评测阶段发生；
- **机器验证**：数值/代数断言经校验引擎（可插拔注册表）重算，宁缺毋滥；
- **溯源**：每条内容带 `source_ref` 与 `verified_by`。

## 架构

| 目录 | 内容 |
|---|---|
| `app/` | 静态 PWA（ES modules：渲染器 / 表达式守卫 / 应用壳），离线可用 |
| `backend/platform.py` | 当前产品后端：静态托管 + PDF 导入流水线 + 账号（SQLite）+ 学习数据 |
| `backend/validation/` | 校验引擎：算法形状注册表（矩阵/特征值/内积/行列式/解方程…） |
| `harness/` | 可插拔提取执行层 + 盲测评测（两段式提取、N 次采样择优、生成-检验） |
| `cores/` | 知识节数据（demo 见上；私有内容自行管理版权） |
| `scripts/` | CI 门禁、onboarding 流水线、机检回填、本地 CI |
| `tests/` | 67 个 Python 单测 + 表达式守卫 node 测试 |

详见 `docs/marrow-design-doc.md`（技术设计）与 `docs/user-guide.md`（使用者手册）。

## 质量门禁

```bash
./scripts/install_hooks.sh   # push 前自动跑：core 门禁 → 单测 → 守卫测试
./scripts/ci_local.sh        # 手动全量体检
```

GitHub Actions workflow 同样就绪（公开仓库 Actions 免费）。

## 路线图

- [ ] OpenStax（CC 授权，可合法分发）章节作为第二个演示 core，演示"任意书"导入路径
- [ ] 更多校验形状进入注册表（复数算术、更多矩阵分解…）
- [ ] 发布页（GitHub Pages）托管静态 PWA

## 版权

- 代码：MIT（见 LICENSE）
- `cores/demo-d1.json`：MIT，可随意修改分发
- **你导入的书籍内容是你自己的衍生品**：本地使用通常没问题，公开分发前请确认对原书的权利

## 致谢

Marrow 的方法论在《Linear Algebra Done Right》（Axler）第四版中译本上完成验证——
该书内容保留在作者的私有实例中，不随本仓库分发。
