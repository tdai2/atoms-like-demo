# Plan — Atoms 风格 AI 应用生成平台

> 本文档是 `mission.md` 的工程落地方案，描述架构、模块划分与技术选型。
> 使命与边界以 `mission.md` 为准；视觉规范以 `app/frontend/DESIGN.md` 为准。

## 一、架构方案

### 1.1 总体思路

产品的核心链路是一条单向流水线：

```
用户意图 → 需求解析 → 方案规划 → 代码生成 → 构建校验 → 测试验证 → 发布预览 → 可访问的应用
              ↑                                                              │
              └──────────────── 对话式增量修改 ←─────────────────────────────┘
```

架构设计围绕两个约束展开：

- **过程必须可观测**：流水线的每个阶段都要有独立、可查询的状态，因此任务状态需要持久化，而不是藏在一次请求的生命周期里。
- **生成必须可迭代**：每个项目保留版本链，新一轮修改基于上一版产物做增量，而非重新生成。

### 1.2 分层架构

```
┌──────────────────────────────────────────────────────┐
│  体验层  React SPA                                    │
│  需求输入台 · 生成时间线 · 预览窗 · 模板库 · 定价      │
└───────────────────────┬──────────────────────────────┘
                        │ HTTPS / JSON
┌───────────────────────┴──────────────────────────────┐
│  接口层  Atoms Cloud Edge Functions (FastAPI)         │
│  鉴权校验 · 任务编排 · 状态查询 · 配额控制             │
└───┬───────────────┬───────────────┬──────────────────┘
    │               │               │
┌───┴────┐   ┌──────┴──────┐   ┌────┴─────────┐
│ 账号    │   │ 数据库       │   │ AI 能力      │
│ Auth   │   │ PostgreSQL  │   │ 文本/图像模型 │
└────────┘   └─────────────┘   └──────────────┘
                    │
              ┌─────┴──────┐
              │ 对象存储    │
              │ 产物/资源   │
              └────────────┘
```

### 1.3 生成流水线的状态模型

生成任务是一个显式状态机，前端轮询任务状态驱动时间线渲染：

| 阶段 | 状态标识 | 产出 | 失败处理 |
|------|---------|------|---------|
| 解析需求 | `parsing` | 结构化需求 `spec_json`（实体、页面、技术栈、名称） | 上游不可用时停在失败阶段并暴露原因 |
| 生成方案 | `planning` | 方案 `plan_json`（文件清单与组件树） | 同上；结构化输出先本地容错，再触发一次模型修复 |
| 编写代码 | `coding` | 单文件应用上传对象存储，写入 `artifact_key` | 同上；不落半成品 |
| 构建校验 | `building` | 结构校验结果写入 `test_report_json` | 结构校验不通过即判定失败并暴露缺失项 |
| 测试验证 | `testing` | 基于真实产物内容生成测试报告（单元 / 冒烟 / 覆盖率） | 同上 |
| 发布预览 | `deploying` | 按对象键解析可访问地址并校验可达 | 地址不可访问即判定失败并暴露原因 |

阶段状态取值为 `pending` / `running` / `done` / `failed`；项目状态取值为 `queued` / `pending` / `running` / `succeeded` / `failed`。

失败不清空任务，而是停在失败阶段并暴露原因——对应 `mission.md` 的「过程透明优于结果惊喜」。

### 1.4 数据模型草案

| 表 | 关键字段 | 说明 |
|----|---------|------|
| `projects` | `id` `user_id` `name` `prompt` `status` `current_stage` `template_key` `latest_version` `spec_json` `plan_json` `artifact_key` `test_report_json` `preview_url` | 一个用户项目 |
| `project_versions` | `id` `user_id` `project_id` `version` `diff_summary` `files_key` | 版本链，支持回溯 |
| `build_tasks` | `id` `user_id` `project_id` `run_no` `stage` `stage_name` `stage_order` `stage_state` `stage_log` `error_message` `output_summary` | 驱动生成时间线，按 `run_no` 分批 |
| `usage_quotas` | `user_id` `period` `plan` `used` `quota_limit` | 按自然月限制生成次数 |
| `test_cases` | `id` `user_id` `project_id` `title` `case_type` `preconditions` `steps` `expected` `assertion` `source` `case_state` | 项目测试用例；`source` 区分自动生成与手动新增，`assertion` 是可在产物源码中匹配的断言片段 |
| `test_runs` | `id` `user_id` `project_id` `status` `triggered_by` `total` `passed` `failed` `duration_ms` `results_json` `error_message` | 每次测试执行的统计与逐用例结果，构成可追溯的测试历史 |
| `users`、`oidc_states` | `id`(=平台 `sub`) `email` `role` / `state` `nonce` `code_verifier` `expires_at` | 平台身份映射与登录临时数据，详见 `docs/backend.md` |

文件产物不入库，存对象存储，库中只保留对象键（`artifact_key` / `files_key`）。`projects.preview_url` 字段保留但**不写入签名地址**：签名链接会过期，预览地址每次请求按 `artifact_key` 即时解析。模板库是后端确定性数据（`GET /api/v1/generation/templates/{key}`），不单独建表。

## 二、模块划分

### 2.1 前端模块（`app/frontend`，阶段一已落地）

| 模块 | 职责 | 关键文件 |
|------|------|---------|
| 路由壳 | 首页与次级页面路由挂载 | `src/App.tsx` |
| 首页 | 输入台、时间线、能力、模板库、定价、CTA | `src/pages/Index.tsx` |
| 顶栏 | 粘性导航与移动端菜单 | `src/components/SiteHeader.tsx` |
| 真实预览 | iframe 加载对象存储产物地址，含加载、空地址与失败状态 | `src/pages/Index.tsx`、`src/pages/ProjectDetail.tsx` |
| 项目页面 | 我的项目列表与项目详情（流水线快照、方案、测试报告、版本、重试、删除） | `src/pages/Projects.tsx`、`src/pages/ProjectDetail.tsx` |
| 账号与入口 | 账号三态、登录 / 注册 / 登出回跳、免费开始意图消费 | `src/hooks/useAuthStatus.ts`、`src/pages/SignIn.tsx`、`src/pages/SignUp.tsx`、`src/pages/LogoutCallbackPage.tsx`、`src/lib/startFree.ts` |
| 测试面板 | 用例生成、执行、运行历史与手动增删改用例 | `src/components/TestSuitePanel.tsx` |
| 占位页 | 未建设模块的统一说明，模板详情复用 | `src/pages/Placeholder.tsx` |
| 静态数据 | 预设提示词、构建步骤、模板、能力、定价、发布记录 | `src/data/site.ts`、`src/data/changelog.ts` |
| 设计系统 | 颜色、字体、网格背景、动效 | `src/index.css` `DESIGN.md` |

### 2.2 后端模块（阶段二已落地）

| 模块 | 职责 | 对外接口 |
|------|------|---------|
| 鉴权 | 会话校验与用户身份解析 | 复用 Atoms 内置账号体系（`dependencies/auth.py`），不自建 |
| 项目管理 | 项目增删改查、版本列表与回溯 | `GET/POST /api/v1/generation/projects`、`/projects/{id}/versions`、`DELETE /projects/{id}` |
| 生成编排 | 创建生成任务、推进阶段、写入状态 | `POST /api/v1/generation/projects`、`GET /api/v1/generation/projects/{id}`、`POST /projects/{id}/retry` |
| 方案推导 | 由需求文本经模型推导页面、实体与技术栈 | `services/generation_ai.py`（`deepseek-v4-flash` 解析、`claude-opus-5` 规划） |
| 后台执行 | 进程内工作器推进阶段、项目去重、启动恢复未完成项目 | `services/pipeline_runner.py` |
| 实体 CRUD | 六张表的自动生成路由，均按用户隔离 | `/api/v1/entities/{projects,build_tasks,project_versions,usage_quotas,test_cases,test_runs}` |
| 测试能力 | 用例生成与手动维护、真实产物上的确定性执行、运行历史查询 | `services/test_suite.py`、`routers/test_suite.py`；`/api/v1/testing/*` |
| 产物存储 | HTML 上传、回读校验、预览地址解析与可达性检查 | `services/generation_artifacts.py`、`services/storage.py`；bucket `generation-artifacts` |
| 配额 | 按自然月校验与计数，条件原子扣减 + 失败退款 | `services/generation.py` 的 `get_or_create_quota` / `consume_quota` / `refund_quota` |

### 2.3 模块依赖方向

```
体验层 → 接口层 → { 鉴权, 项目管理, 生成编排 }
                      生成编排 → AI 调用 → 模型
                      生成编排 → 产物存储 → 对象存储
                      生成编排 → 配额
                      接口层 → 后台工作器 → 生成编排（异步推进，独立短会话）
```

依赖单向向下，禁止反向调用；AI 调用只被生成编排使用，保证模型替换不外溢。后台工作器只调用生成编排的阶段推进函数，不直接触碰模型与对象存储细节。

## 三、技术选型

### 3.1 前端

| 选型 | 方案 | 理由 |
|------|------|------|
| 构建 | Vite | 启动与热更新快，产物体积可控 |
| 框架 | React + TypeScript | 生态成熟，类型保障生成逻辑的数据契约 |
| 样式 | Tailwind CSS | 与设计令牌天然对应，避免样式文件膨胀 |
| 组件 | shadcn/ui | 源码级可控，不引入难以定制的黑盒 |
| 路由 | react-router-dom | SPA 标准方案，占位页可按路由逐个替换 |
| 图标 | lucide-react | 线性风格与工程感视觉一致 |
| 状态 | React 内置状态 | 当前无跨页共享需求，不引入状态库 |
| 数据请求 | TanStack Query | 接入后端后承担轮询、缓存与重试 |

### 3.2 后端

| 选型 | 方案 | 理由 |
|------|------|------|
| 运行时 | Atoms Cloud Edge Functions | 免运维，与账号、存储、AI 同源 |
| 语言 | Python (FastAPI) | 平台原生支持，适合编排类逻辑 |
| 数据库 | PostgreSQL | 关系清晰，版本链与配额需要事务保证 |
| 鉴权 | Atoms 内置账号体系 | 不自建第二套登录，避免安全面扩大 |
| 存储 | Atoms 对象存储 | 生成产物与预览资源统一托管 |
| 模型 | `claude-opus-5` 负责方案与代码生成 | 代码能力强，适合结构化产出 |
| 模型 | `deepseek-v4-flash` 负责需求解析 | 轻量快速，控制单次生成成本 |

### 3.3 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 生成任务同步还是异步 | 异步 + 轮询 | 生成耗时长，同步请求会超时且无法展示过程 |
| 预览窗形态 | iframe 加载对象存储中的真实产物 | 生成结果已是可运行应用，iframe 才能如实呈现，避免用本地组件冒充产物 |
| 模板缩略图 | CSS 线框 | 避免无意义配图，保持工程风一致 |
| 生成推进方式 | 服务端阶段状态 + 后台工作器 + 前端轮询 | 过程可查询、刷新不丢失；创建请求立即返回，慢调用不占用请求生命周期 |
| 是否自建管理后台登录 | 否 | 用账号角色区分权限，不做第二套认证 |
| 产物是否入库 | 否，存对象存储，库中只留对象键 | 避免大字段拖垮数据库性能 |
| 产物地址是否入库 | 否，按对象键即时解析 | 签名地址有有效期，持久化会产生失效链接 |
| 慢调用事务边界 | AI 与对象存储调用前后不持有数据库事务 | 长事务占用连接池会与并发轮询争抢，放大为网关 502 |
| 配额并发保护 | 条件原子更新扣减，模型失败退款 | 并发首次创建不超扣，外部模型不可用时不白扣用户额度 |
| 阶段并发保护 | 数据库原子抢占 + `600` 秒陈旧阶段回收 | 多端轮询与多进程部署都不会重复执行同一阶段 |

## 四、实施计划

| 阶段 | 范围 | 交付标志                      |
|------|------|---------------------------|
| 一（已完成） | 纯前端演示：输入台、时间线、预览窗、模板库、定价 | 三十秒内理解产品主张                |
| 二（已完成） | 激活后端，落地账号、项目表、生成接口 | 登录后能看到自己的项目列表             |
| 三（已完成） | 接入真实模型生成、后台异步执行与可靠性加固 | 输入任意需求产出可访问链接             |
| 四 | 测试用例生成、执行与结果记录 | 可以自动或手动生成测试用例，执行并查询历史测试记录 |
| 五 | Bug 提交、记录与自动修复 | 能提交 bug、记录 bug，并尝试自行解决    |
| 六 | 对话式增量修改、版本回溯 | 追加需求只改动对应部分               |
| 七 | 自定义域名、团队协作与权限 | 项目可对外正式发布                 |

### 阶段一交付清单

| 交付项 | 落地位置 |
|--------|---------|
| 需求输入台（预设胶囊、⌘/Ctrl + Enter、空输入禁用态） | `app/frontend/src/pages/Index.tsx` |
| 六阶段生成时间线与定时推进状态机 | `app/frontend/src/pages/Index.tsx`、`src/data/site.ts` |
| 应用预览窗与测试报告面板 | `src/pages/Index.tsx`、`src/data/site.ts`（阶段三起预览窗改为 iframe，原模拟预览组件已移除） |
| 能力介绍、模板库与分类筛选、定价、CTA | `src/pages/Index.tsx`、`src/data/site.ts` |
| 次级占位页（模板详情、文档、计费） | `src/pages/Placeholder.tsx`、`src/App.tsx` |
| 暗色工程风设计系统与动效、可访问性 | `src/index.css`、`DESIGN.md` |

阶段一的占位页中，「更新日志」与「登录」已在阶段二替换为真实页面，占位页只保留模板详情、文档中心与计费三处。

验证方式：`pnpm run lint` 与 `pnpm run build` 均通过；首页与 `/blog/` 完成预渲染。

### 阶段二交付清单

| 交付项 | 落地位置 |
|--------|---------|
| 数据表：项目、六阶段任务、版本链、按周期配额 | `projects`、`build_tasks`、`project_versions`、`usage_quotas` |
| 生成编排服务：方案推导、阶段推进、配额扣减、失败与重试 | `app/backend/services/generation.py` |
| 生成自定义接口（创建 / 列表 / 详情 / 重试 / 删除 / 版本 / 模板方案） | `app/backend/routers/generation.py` |
| 前端接口层与数据 Hook（查询、轮询、创建、重试、删除） | `app/frontend/src/lib/projects.ts`、`src/hooks/useProjects.ts` |
| Atoms 账号三态接入与真实登录入口 | `src/hooks/useAuthStatus.ts`、`src/pages/SignIn.tsx` |
| 我的项目列表页（加载 / 未登录 / 空列表 / 失败重试 / 成功列表） | `src/pages/Projects.tsx` |
| 项目详情页（流水线快照、方案、测试报告、失败重试） | `src/pages/ProjectDetail.tsx` |
| 首页生成链路改为创建任务 + 轮询服务端阶段状态 | `src/pages/Index.tsx` |
| 更新日志页与发布记录数据源（最新 `v0.8.0` 覆盖真实生成与可访问产物） | `src/pages/Changelog.tsx`、`src/data/changelog.ts` |
| 顶栏账号区（登录 / 免费开始 / 账号邮箱 / 退出登录）与登出降级 | `src/components/SiteHeader.tsx`、`src/hooks/useAuthStatus.ts`、`app/backend/routers/auth.py` |

验证方式：后端 Python 语法检查通过；`pnpm run lint` 与 `pnpm run build` 通过。

### 阶段三交付清单

| 交付项 | 落地位置 |
|--------|---------|
| 真实模型调用：需求解析 `deepseek-v4-flash`，方案规划与代码编写 `claude-opus-5` | `app/backend/services/generation_ai.py` |
| 模型硬超时（180 秒）、上游异常收敛为可读业务错误、结构化输出容错（JSON 块提取、尾随逗号清理、截断补全、一次修复） | `app/backend/services/generation_ai.py` |
| 六阶段由真实执行结果驱动，失败落在失败阶段并暴露原因 | `app/backend/services/generation.py` |
| 后台工作器：项目去重、限时 kick、启动恢复未完成项目 | `app/backend/services/pipeline_runner.py` |
| 产物上传、回读校验与预览地址可达性检查（bucket `generation-artifacts`，键 `projects/{id}/v{n}/index.html`） | `app/backend/services/generation_artifacts.py` |
| 预览窗切换为 iframe，含加载、空地址、失败与重试状态 | `src/pages/Index.tsx`、`src/pages/ProjectDetail.tsx` |
| 配额条件原子扣减与模型失败退款、阶段原子抢占与 `600` 秒陈旧回收 | `app/backend/services/generation.py` |
| 网关 502/524 修复：阶段短事务、连接池调参、请求归还连接后再等待工作器 | `app/backend/services/generation.py`、`app/backend/core/database.py`、`app/backend/routers/generation.py` |
| 登出回跳路由 `/logout-callback`，并移除无引用的模拟预览组件 | `src/pages/LogoutCallbackPage.tsx`、`src/App.tsx` |

验证方式：`verify_stage3.py`（真实 AI、上传 `200`、回读成功、预览地址 `200`、无 iframe 阻断头）、`verify_pipeline.py`（状态 `succeeded`、结构校验 `5/5`、冒烟 `4/4`、版本与重试不重复扣额）、`verify_quota_refund.py`（模型失败退款且无残留）、`verify_gateway_timeout.py`（创建与并发轮询耗时、无 `5xx`）。

阶段三起预览地址按对象键即时解析，`projects.preview_url` 不落库；重试复用已落库的 `spec_json`，不再重复消耗解析阶段。生成接口与配额校验的契约保持不变，前端调用方式未改动。

### 阶段四交付清单

| 交付项 | 落地位置 |
|--------|---------|
| 测试用例生成：基于已落库方案与对象存储回读的真实产物，由 `claude-opus-5` 产出 6-10 条用例 | `app/backend/services/generation_ai.py` 的 `write_test_cases`、`app/backend/services/test_suite.py` 的 `generate_cases` |
| 用例字段契约：标题、类型（结构 / 交互 / 内容）、前置条件、步骤、预期、断言片段、来源、启用状态 | `app/backend/models/test_cases.py` |
| 真实执行：在产物源码上做确定性断言匹配，通过与否由产物决定，不由模型判定 | `app/backend/services/test_suite.py` 的 `execute_run` |
| 执行记录：状态、总数、通过数、失败数、耗时、逐用例结果与失败原因 | `app/backend/models/test_runs.py` |
| 用例手动维护：新增、编辑、启用 / 停用、删除；停用用例不参与执行 | `app/backend/routers/test_suite.py` |
| 测试接口：面板快照、生成用例、用例 CRUD、执行、单次运行详情 | `GET /api/v1/testing/projects/{id}/suite`、`POST /cases/generate`、`POST /cases`、`PUT/DELETE /cases/{id}`、`POST /runs`、`GET /runs/{id}` |
| 项目详情页测试面板：生成、执行、结果统计、运行历史切换、手动增删改、加载 / 空 / 错误 / 成功态 | `src/components/TestSuitePanel.tsx`、`src/pages/ProjectDetail.tsx` |
| 项目删除同步清理测试用例与运行记录 | `app/backend/services/test_suite.py` 的 `purge_project_tests` |

验证方式：`verify_test_suite.py`（无产物项目拒绝生成与执行、通过 / 失败统计与产物一致、停用用例被排除、运行历史倒序、跨用户隔离、删除用例不影响历史、项目删除清理干净）与后端 `py_compile`、前端 `pnpm run lint && pnpm run build`。用例生成的真实模型调用同样受平台 AI 余额约束，余额不足时会明确失败而不是伪造通过。

### 未完成事项

- 生产启动脚本 `app/start_app_v2.sh` 的后端命令仍带 `--reload`，生产部署需去掉。
- 删除项目目前只清理业务表，不清理对象存储产物，会产生孤儿对象。
- 进程内后台工作器适合常驻进程；若改为无服务器形态，需评估请求结束后任务被冻结的风险。
- 历史额度消耗与项目记录不一致的排查结论见 `.atoms/PROGRESS.md`。