# Marrow — AI时代技术科普阅读方法论 完整产品方案 v0.2

> 这份文档取代v0.1，整合了从方法论讨论、Phase 0真实验证、schema定型、到PWA原型跑通为止的全部内容和决策。产品名暂定Marrow，正式使用前需完成商标/域名检索。

> **2026-10 状态注记**：Phase 2 核心已落地——内容扩展提前完成（全书 26 节）、
> 账号与多设备同步（SQLite 实现，schema 对齐 4.4 节设计）、core 版本留痕、
> harness 独立产出盲测验收通过（2A vs 基线，案例召回 100%）、26/26 节探索可视化。
> PostgreSQL 平移与审核 UI 按文档原则推迟到真实需要时；公开部署仍待版权决策。


## 一、产品定位

把技术/科普类书籍或论文，转化为可探索式交互学习与实战应用工具的平台。核心主张：用AI自动化"从文本提取知识结构 → 建立可运行的数学模型 → 生成可探索的交互界面"这条流水线，替代传统电子书"一页一页翻"的阅读方式。

**这个产品唯一真正novel、也是Phase 0已经拿到正面证据的赌注**：AI能不能把"人工精心手作一份可探索式讲解"这件事自动化到可用质量，并泛化到任意一本技术科普书。Phase 0已经证明：提取忠实度、算法可执行性、探索式交互，三件事在真实书籍（LADR线性代数）上都站得住。

## 二、核心理念

- **干中学（learning by doing）**：算法/模型在用户动手前已经确定，用户可以直接用书中方法解决实际问题。
- **就地补概念，用户自主判断**：studio不代替用户判断认知卡点，只负责把所有相关探索路径摊开，方便进出。
- **Explorable Explanations（Bret Victor）**：交互要能触及模型的底层参数/结构，不是点击翻页式的浅层交互。
- **studio兼具学习与实战应用双重定位**：用户可能拿它做真实决策，模型准确度要求比纯教学工具更高。
- **例题与习题分工不同**：原文给出解的"例"用于模型验证；原文不给解的"习题"是用户在studio里实战的地方——这是Phase 0实测发现的、原设计没有的区分。

## 三、适用范围

限定为技术/科普类书籍和论文。评估环节前置：导入后先判断是否适用，不适用的路由到其他方法，不强行走完整流程。

## 四、产品架构

### 4.1 Studio
通用探索型交互引擎，遵循Explorable Explanations理念。已用真实数据验证：同一套渲染代码（parameters+outputs的expr求值机制）能同时驱动"连续参数可调"和"定义驱动构造"两种探索形态，无需为每本书写专属渲染代码。目前边界：数值/文本类输出可通用渲染，自定义几何可视化（如SVG图形变换）仍需专属实现，尚未通用化。

### 4.2 Harness
驱动提取、建模、验证与动态迭代的执行层。当前阶段（内容验证期）由AI助手直接承担这个角色，产品正式接入harness时按"可自定义"设计，候选包括Codex等，接入方式见下方Phase 2。

### 4.3 Core
每本书/每个小节对应studio上的一个core，标准schema已定型（marrow-core-schema-v1.json），字段包括dictionary、structure、algorithms、explorable、cases（区分role=validation/practice）、related_cores（支持知识扩散式跨core导航，已用真实案例验证可行）。

### 4.4 后端与数据层（新增，此前被简化掉，现在补全）

**现状（Phase 0-1）**：纯静态PWA，core是静态JSON文件，没有用户状态、没有数据库——这个阶段够用，因为没有需要持久化的用户专属数据。

**这不是最终形态，以下是完整的后续设计：**

**数据库选型**：PostgreSQL + JSONB。理由：core内容本身是灵活的嵌套JSON（适合JSONB），但用户进度、审核流程、多用户关系这些需要事务和关系完整性（适合关系型）——两者都要，Postgres的JSONB字段刚好覆盖这个混合需求，不必在"纯文档库"和"纯关系库"之间二选一。

**核心表结构**：

- `users(id, email, created_at, ...)`
- `cores(id, topic, source_book, source_section, active_version_id, created_at, updated_at)` — 只存当前生效版本的指针
- `core_versions(id, core_id, version_number, data JSONB, extracted_by, review_status[pending/approved/rejected], reviewed_by, created_at)` — **这张表就是harness驱动动态迭代的落地机制**：每次harness产出新提取，写一条pending记录，不直接覆盖线上内容；人工或自动校验（比对`cases[].role=validation`的computed_check）通过后才置为approved并更新`cores.active_version_id`；被拒绝的版本保留用于追溯，不删除。
- `user_progress(id, user_id, core_id, status, last_interacted_at)` — 支撑web/dmg/app三端的进度同步，这是跨设备体验成立的前提，静态站点做不到这件事。
- `case_attempts(id, user_id, case_id, submitted_answer, is_correct, attempted_at)` — 用户在practice类案例（习题）里的实战记录。

**API层**（REST，简化列出）：
- `GET /api/cores`、`GET /api/cores/:id` — 面向用户，只读已发布版本
- `POST /api/progress`、`GET /api/progress/:user_id` — 进度同步
- `POST /api/cases/:id/attempt` — 提交习题答案
- `POST /api/cores/:id/versions`（管理端）— harness提交新提取版本
- `POST /api/cores/:id/versions/:vid/approve`（管理端）— 审核通过并发布

**什么时候接入**：不是现在，是Phase 2开始时——原因不是"图省事"，是**现在还没有任何东西需要数据库解决**（没有用户账号、没有跨设备同步需求、没有真正的harness自动化迭代在跑），提前搭建等于在给未验证的假设做架构投入。但Phase 2一旦启动，后端是明确排进计划的，不是模糊带过。

**校验引擎（本节新增，已实现并测试）**：`core_versions`表新增`validation_result`字段。harness提交新版本时（`POST /api/cores/:id/versions`），后端自动跑一个可复用的校验引擎（`validation/verifiers.py`注册表 + `run_validation.py`通用runner）——cases里带`verify`声明的验证案例会被自动重算并比对期望值，结果连同pending版本一起存下来，审核者在批准前就能看到哪些案例过了、哪些没过，不用凭感觉审核。已实测：正常提取自动通过，人为构造的错误提取会被自动标记FAIL，审核端可以直接`reject`，不需要等人工肉眼发现问题。这是"harness驱动动态迭代"这句话里，"驱动"具体如何落地的机制，此前一直是空的。

**已知边界**：校验引擎是注册表模式，不是无限泛化——新的算法形状（比如涉及复数域的案例，5A的例5.9目前就还覆盖不到）出现时，需要往`verifiers.py`里加一个新函数并注册，不是零成本自动适配所有数学结构。这个边界要如实承认，不能说成"全自动"。

## 五、核心流程（六步法）

1. 建立studio，接入AI模型和harness（Explorable Explanations理念）
2. 导入电子书/论文，AI评估适用性
3. AI提炼词典/体系结构/算法/案例
4. 用词典对齐术语，用体系结构和算法建立数学模型core
5. 用真实案例验证并持续优化，由harness驱动（生产环境下即上述core_versions审核流程）
6. 用户在studio直接应用理论解决实际问题（对应习题/practice cases），并触发知识扩散式学习（对应related_cores跨core导航）

## 六、Phase 0 验证结论（已完成）

试点书籍：《Linear Algebra Done Right》第四版中译本，测试了3A-3C节（常规内容）和5A节（本书最反套路的行列式后置处理）。

- 提取忠实度：有具体证据（矩阵在提取结果里始终依赖"线性映射+基"而非独立几何对象；5A的特征值判据完全不用行列式），不是靠通用知识蒙的。
- 算法可执行性：矩阵构造、特征向量判定等，均已写成代码，对照原书例题逐位验证一致。
- 探索交互：两种形态（连续参数可调、定义驱动构造）都做出了真实可用的实现。
- 新发现：例题/习题需要在schema里分开处理（role字段）；案例充足程度需要逐节实测，不能按章节类型预判。

完整报告：`phase0-validation-report.md`。

## 七、Phase 1 验证结论（已完成）

- `marrow-core-schema-v1.json` 已定型，基于两份真实core反推。
- 通用渲染器已验证：同一套引擎代码，切换core数据即可呈现完全不同的交互体验，零专属代码。
- 一个真实可部署的静态PWA（`marrow-app.zip`）已构建完成并经过功能测试：manifest、service worker离线缓存、多core导航、related_cores跨core跳转，全部跑通，默认参数下的计算结果与原书例题精确一致。
- 已知边界：目前只有2节内容；自定义几何可视化尚未通用化。

## 八、完整开发路线图

### Phase 0 — 单点验证 ✅ 已完成
方法论可行性验证，见第六节。

### Phase 1 — Schema定型与可运行原型 ✅ 已完成
core标准schema、通用渲染器、静态PWA骨架，见第七节。

### Phase 2 — 后端接入 + Harness生产化 + 内容扩展（下一阶段）
- 搭建API层 + PostgreSQL，把静态core JSON迁移进`cores`/`core_versions`表。
- 实现用户账号与`user_progress`，作为web/dmg/app三端同步的前提。
- 实现`core_versions`审核流程，这是harness真正投入生产、支持"动态迭代"的落地机制。
- 接入实际harness（Codex或其他，按第4.2节"可自定义"设计），用本报告Phase 0人工校验过的3A-3C提取结果做基准比对，检验harness独立产出的质量。
- 按已经跑通两次的流程（定位页码→提取→代码验证→存版本）持续扩展内容，覆盖LADR更多章节。

### Phase 3 — 多端与规模化
- Web PWA打磨到可对外发布的完成度。
- macOS dmg（Electron/Tauri包装现有Web应用）、移动端app跟进。
- 内容覆盖扩展到全书，通用几何可视化能力补齐。
- 视验证结果决定是否扩展到缠论等其他领域，检验studio在非数学类技术内容上的通用性。

## 九、风险提示

- Phase 2引入后端和harness生产化是这套系统里工程量最大的一段，涉及审核流程、版本管理，需要按明确的表结构和API去实现，不能临场设计。
- 缠论若作为后续试点，需接受"验证结果更多反映缠论本身难度，而非方法论通用性"这一局限。
- Codex的Agents API等外部harness仍在快速迭代期，接入时建议做适配封装层，降低未来切换成本。
