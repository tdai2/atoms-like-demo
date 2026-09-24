---
last_updated: 2026-09-22T07:20:00Z
---

# Requirements & Progress

## Requirements Overview

依据 `docs/mission.md` 与 `docs/plan.md` 落地阶段一：Atoms 风格 AI 应用生成平台的**纯前端演示版**。目标是在三十秒内让用户理解「一句话 → 生成可运行应用」的产品主张，并看到完整演示链路。

阶段二在此之上接入 Atoms Cloud：账号复用平台内置认证，项目、六阶段任务、版本与配额落库，生成链路改为「创建任务 + 轮询服务端状态」。交付目标是登录用户能看到归属自己的项目列表。

阶段三把生成链路替换为真实实现：六个阶段由真实模型调用驱动，产物写入对象存储并以 iframe 预览；同时完成异步执行、配额原子扣减与失败退款、阶段原子抢占与陈旧回收、慢调用前后拆分事务等可靠性加固。交付目标是输入任意需求即可得到可访问的真实应用，且外部模型异常时不白扣额度、不留半成品。

## User Stories

- 作为访客，我能在首屏输入一句自然语言需求，并看到生成过程被逐步推进。
- 作为访客，我能在生成过程中看到六个阶段的实时状态（含测试验证）。
- 作为访客，我能在预览窗看到生成出的真实界面，而不是静态图片。
- 作为访客，我能浏览模板库、按分类筛选，并进入模板详情。
- 作为访客，我能查看定价方案并进入订阅页（建设中说明）。
- 作为登录用户，我能在「我的项目」看到归属当前账号的项目列表，并区分加载中、未登录、空列表与失败重试状态。
- 作为登录用户，我能从列表进入项目详情，查看六阶段流水线快照、方案与测试报告。
- 作为登录用户，我能删除自己的项目，并在项目失败后重试而不重复消耗额度。
- 作为登录用户，我能看到本周期已用/总额度，额度用尽时收到明确提示而不是静默失败。

## Task Breakdown
| ID | Task | Assignee | Status | Deps |
|----|------|----------|--------|------|
| P1-1 | 前端工程初始化（Vite + React + TS + shadcn/ui） | Alex | done | - |
| P1-2 | 首屏 Prompt Console：输入、预设胶囊、⌘+Enter、禁用态 | Alex | done | P1-1 |
| P1-3 | 生成时间线：六阶段 pending/running/done 三态与定时推进 | Alex | done | P1-2 |
| P1-4 | 预览窗：三类迷你应用真实 DOM 渲染 + 状态徽标 + 测试报告 | Alex | done | P1-3 |
| P1-5 | 能力介绍、模板库与分类筛选、模板详情占位 | Alex | done | P1-1 |
| P1-6 | 定价区块与次级占位页（文档/登录/计费/更新日志） | Alex | done | P1-1 |
| P1-7 | 设计系统落地：暗色工程风 tokens、网格背景、动效与可访问性 | Alex | done | P1-1 |
| P1-8 | 更新日志页：发布记录数据源、类型筛选与版本跳转 | Alex | done | P1-1 |
| V1-1 | Lint 与生产构建验证 | Alex | done | P1-7 |
| V1-2 | 界面渲染与生成链路验证 | Alex | done | V1-1 |
| P2-1 | 激活 Atoms Cloud 后端与项目相关数据表 | Alex | done | V1-2 |
| P2-2 | 项目 / 任务 / 版本 / 配额四组 ORM、服务与实体 CRUD 路由 | Alex | done | P2-1 |
| P2-3 | 生成编排服务：方案推导、六阶段任务、版本记录、配额扣减、失败与重试 | Alex | done | P2-2 |
| P2-4 | 生成自定义接口：创建、列表、详情、重试、删除、版本与模板方案 | Alex | done | P2-3 |
| P2-5 | 前端接口层与数据 Hook（`lib/projects.ts`、`hooks/useProjects.ts`） | Alex | done | P2-4 |
| P2-6 | Atoms 账号三态接入（`hooks/useAuthStatus.ts`、`/signin` 真实登录页） | Alex | done | P2-5 |
| P2-7 | 「我的项目」列表页：加载/未登录/空列表/失败重试/成功列表 | Alex | done | P2-6 |
| P2-8 | 项目详情页：流水线快照、方案、测试报告、失败重试 | Alex | done | P2-6 |
| P2-9 | 首页生成链路替换为创建任务 + 轮询服务端阶段状态 | Alex | done | P2-8 |
| V2-1 | Python 语法检查（新增服务、路由与模型文件） | Alex | done | P2-4 |
| V2-2 | Lint 与生产构建验证 | Alex | done | P2-9 |
| V2-3 | 界面渲染验证 | Alex | done | V2-2 |
| P2-10 | 统一前端认证上下文：`AuthContext` 与 `useAuthStatus` 同源 `client.auth.*`，隔离遗留 Axios 链路 | Alex | done | P2-9 |
| P2-11 | 文档同步：前端 README、`.wiki.md`、根 README 更新至阶段二状态 | Alex | done | P2-10 |
| P2-12 | 「免费开始」入口接通真实链路：未登录先登录、登录后回到首页需求输入区并聚焦 | Alex | done | P2-11 |
| V2-4 | Lint、生产构建与界面渲染验证（免费开始入口改动后） | Alex | done | P2-12 |
| P2-13 | 认证入口改造：新增 `/signup` 注册落地页，未登录「免费开始」改为进入注册页而非登录页 | Alex | done | P2-12 |
| P2-14 | 顶栏账号区：已登录显示账号邮箱与「退出登录」（`client.auth.logout()`），未登录显示「登录 / 免费开始」，桌面端与移动端统一 | Alex | done | P2-13 |
| V2-5 | 回归验证：lint、生产构建、界面渲染检查，并用浏览器实测未登录「免费开始」落入 `/signup` 注册页（登录态渲染分支代码复核） | Alex | done | P2-14 |
| P2-15 | 更新日志追加 `v0.7.0` 发布记录：账号体系与项目持久化、顶栏账号区、额度视图与登出修复 | Alex | done | P2-14 |
| P2-16 | 文档同步：`docs/plan.md` 阶段一占位页范围、阶段二交付清单，前端 README 发布记录约定，根 README 当前进度 | Alex | done | P2-15 |
| V2-6 | Lint、生产构建与 `/changelog` 页面渲染验证（发布记录更新后） | Alex | done | P2-16 |
| P3-1 | 真实 AI 生成服务：需求解析 `deepseek-v4-flash`、方案规划与代码编写 `claude-opus-5`、JSON 一次修复与字段校验 | Alex | done | V2-6 |
| P3-2 | 对象存储产物链路：HTML 上传、回读校验、预览地址解析与可访问性检查（`generation-artifacts`） | Alex | done | P3-1 |
| P3-3 | 生成编排替换模拟流程：六阶段由真实调用驱动，阶段结果与失败日志落库 | Alex | done | P3-2 |
| P3-4 | 前端预览切换真实 iframe：加载、空地址、失败与重试状态 | Alex | done | P3-3 |
| P3-5 | 可靠性加固：配额条件原子扣减、模型失败退款、阶段原子抢占、`600` 秒陈旧阶段回收、慢调用前后拆分事务 | Alex | done | P3-3 |
| P3-6 | 认证链路回归：补上 `/logout-callback` 回跳路由，统一登出后返回首页体验 | Alex | done | P3-4 |
| P3-7 | 清理无引用的关键词模拟预览组件（`MiniApp.tsx`） | Alex | done | P3-4 |
| V3-1 | 真实 AI 与对象存储验证：上传 `200`、回读成功、预览地址 `200`、无 iframe 阻断头（`verify_stage3.py`） | Alex | done | P3-5 |
| V3-2 | 六阶段流水线验证：状态 `succeeded`、结构校验 `5/5`、冒烟 `4/4`、覆盖率 `86%`、重试 `run_no` 递增不重复扣额（`verify_pipeline.py`） | Alex | done | V3-1 |
| V3-3 | 后端语法检查（`py_compile`）与前端 `pnpm run lint && pnpm run build` | Alex | done | P3-6 |
| P3-8 | 文档归档：前端开发文档与更新日志文档迁入 `docs/`（`docs/frontend.md`、`docs/changelog.md`），根 README、`.wiki.md` 与 `.atoms/ARCHITECTURE.md` 索引同步 | Alex | done | V3-3 |
| P3-9 | 更新日志补齐 `v0.8.0`（真实生成与可访问产物）：真实模型六阶段、对象存储 iframe 预览、后台异步执行、配额退款、542/502 修复等阶段三交付，`docs/changelog.md` 与数据源同步 | Alex | done | P3-8 |
| P3-10 | 后续阶段顺序调整：原阶段四（对话式增量修改与版本回溯）后移至阶段六，测试用例生成与 Bug 自动修复各前移一阶段；`docs/plan.md`、`docs/frontend.md`、`app/frontend/README.md`、`docs/mission.md` 与上下文文件同步 | Alex | done | P3-9 |
| P4-1 | 测试用例与运行记录数据表：`test_cases`、`test_runs` 按用户隔离重建，并与平台流程适配（`source` 区分自动/手动、`case_state` 控制启用、`results_json` 存逐例明细） | Alex | done | P3-10 |
| P4-2 | 测试用例生成：基于已落库方案与对象存储回读的真实产物，由 `claude-opus-5` 产出 6-10 条结构化用例，重复生成替换自动用例并保留手动用例 | Alex | done | P4-1 |
| P4-3 | 测试执行服务：在当前产物源码上做确定性断言匹配，产出总数/通过数/失败数/耗时与逐例结果；停用用例不参与执行 | Alex | done | P4-2 |
| P4-4 | 测试接口与用例 CRUD：面板快照、生成、新增、编辑、启用停用、删除、执行与单次运行详情，全部按用户隔离 | Alex | done | P4-3 |
| P4-5 | 项目删除同步清理测试用例与运行记录 | Alex | done | P4-4 |
| P4-6 | 前端接口层与 mutations：测试套件查询、生成、CRUD、执行与运行详情接入 `src/lib/projects.ts`、`src/hooks/useProjects.ts` | Alex | done | P4-4 |
| P4-7 | 项目详情页测试面板：生成、执行、结果统计、运行历史切换、手动增删改，覆盖加载/无产物/无用例/失败/成功态 | Alex | done | P4-6 |
| V4-1 | 阶段四链路验证 `verify_test_suite.py`：无产物项目拒绝生成与执行、通过/失败统计与产物一致、停用用例被排除、运行历史倒序、跨用户项目与运行访问均被拒、删除用例不影响历史、项目删除后清理干净 | Alex | done | P4-7 |
| V4-2 | 后端语法与路由导入检查（14 个路由模块全部导入成功）、前端 `pnpm run lint && pnpm run build` 通过 | Alex | done | P4-7 |
| P4-8 | 文档同步：`docs/plan.md`（数据模型、模块划分、阶段四交付清单）、`docs/backend.md`（数据模型、测试接口清单、验证脚本）、`docs/frontend.md` 与 `app/frontend/README.md`（关键文件、接口契约、测试能力说明） | Alex | done | V4-2 |

## Progress Log

- 2026-09-23 阶段五实现落地：新增 `models/bugs.py`、`models/bug_fix_logs.py`（两张表均带 `user_id` 隔离），`services/bug_fix.py` 负责缺陷创建/编辑/关闭重开、自动修复调度、修复历史与项目级清理，`routers/bug_fix.py` 暴露 `/api/v1/bugs` 六个接口（面板、创建、更新、删除、触发修复、修复历史）。自动修复链路为「短事务落修复中 → 回读产物并交模型改写（不持有事务）→ 新版本上传与可达性校验 → 短事务落版本并前移项目指针与修复记录 → 在新产物上重跑启用用例复测 → 回写复测结论与缺陷状态」；模型或对象存储失败时如实落一条失败修复记录，缺陷停在可见失败态，且不改动项目版本与产物指针。
- 2026-09-23 阶段五前端接入：新增 `components/BugPanel.tsx`（提交/编辑缺陷、严重级别与关联用例、自动修复、关闭与重开、删除确认、修复历史展开、状态统计、加载/无产物/空/错误态），`lib/projects.ts` 增加阶段五类型与六个接口封装，`hooks/useProjects.ts` 增加 `useBugPanel/useCreateBug/useUpdateBug/useDeleteBug/useFixBug/useBugFixes`（自动修复禁用自动重试，成功后同时刷新缺陷面板、测试面板与流水线），`pages/ProjectDetail.tsx` 接入面板并复用测试套件查询提供关联用例选项。修复后复测的运行记录以 `triggered_by="fix"` 落库，测试面板对应用「修复后复测」展示。
- 2026-09-23 阶段五验证脚本 `verify_bug_fix.py`：覆盖无产物项目拒绝提交缺陷、无效关联用例被拒、失败修复如实落库且不改动项目版本与产物、面板统计与缺陷状态一致、编辑/关闭/重开、跨用户读取面板与修复历史均被拒、真模型修复成功时产出新版本并按关联用例给出复测结论（模型不可用时明确跳过且不伪造成功）、项目删除后缺陷与修复记录清理干净。
- 2026-09-23 阶段五验证通过（`verify_bug_fix.py`，`ALL_CHECKS_DONE`）：无产物项目提交缺陷被拒、无效关联用例被拒、产物不可读时修复如实落失败记录（`386ms`，`target_version=2`）且项目版本与产物指针保持不变、面板统计与缺陷状态一致、编辑/关闭/重开生效、跨用户读取面板与修复历史均被拒（`404`）、项目当前产物回读与地址可达（`293` 字节）、项目删除后缺陷与修复记录清零。真模型修复步骤因平台 AI 余额不足（`insufficient_ai_balance`，HTTP `403`）如实跳过：缺陷停在 `fix_failed`、尝试次数累加为 `1`、项目版本与产物指针未被改动，未伪造修复成功。
- 2026-09-23 阶段五验证复跑通过（`verify_bug_fix.py`，`ALL_CHECKS_DONE` + `CLEANUP_DONE`）：13 个步骤全部按预期，产物不可读路径的失败修复 `627ms` 如实落库，项目当前产物回读 `293` 字节且地址可达，项目删除后缺陷与修复记录清零；脚本 `finally` 段新增验证对象回收，每次运行不再在对象存储留下孤儿产物。同步在 `services/generation_artifacts.py` 增加 `delete_object()`（复用 `StorageService.delete_object`），作为版本清理与验证数据回收的统一下沉能力。真模型修复仍因平台 AI 余额不足（`insufficient_ai_balance`，HTTP `403`）如实跳过，未伪造成功。
- 2026-09-23 界面校验记录：渲染检查截取到的是需登录才能进入的项目详情页（`/projects/:id` 对匿名访客展示「登录后查看项目」，正文含六阶段流水线、方案、测试报告、iframe 预览、测试面板与缺陷面板，均挂在 `state === 'authenticated'` 分支下），因此自动检查无法看到面板本体；缺陷面板接入经代码核对确认完整（`BugPanel` 以 `project.id` 与 `state === 'authenticated'` 传入，并复用 `useTestSuite` 提供关联用例），前端 `pnpm run lint && pnpm run build` 通过（预渲染 `/` 与 `/blog/`）。已登录态的人工体验验证仍待补做。
- 2026-09-23 只读持久化审计（未改代码、未构建）：`users` 1 行（`1606800`），`projects`／`build_tasks`／`project_versions` 均为 0 行，`usage_quotas` 2 行（`1606800` 已用 1，`verify-stage3-user` 已用 0）；四张表均有 `user_id` 索引且无孤立任务／版本、无用户归属错配。对象存储 bucket `generation-artifacts` 残留 3 个对象：空键占位、`projects/2/v1/index.html`（12292 B，2026-09-23T07:47:06Z）、`verify/stage3/healthcheck.html`（239 B）。结论：当前无任何账户存在已持久化项目；账号 `1606800` 额度已扣 1 但无项目行，与「生成后被删除」一致，且删除接口只清理业务表、未清理对象存储产物，故遗留 `projects/2/...` 孤儿对象；`verify-stage3-user` 的配额行为验证脚本残留、`users` 表中无对应用户。
- 2026-09-23 阶段三收尾完成：六个阶段由真实 AI 驱动（需求解析 `deepseek-v4-flash`、方案规划与代码编写 `claude-opus-5`），生成的单文件应用上传至对象存储 `generation-artifacts`（键 `projects/{id}/v{n}/index.html`），预览窗改为真实 iframe；数据库只存对象键 `artifact_key`，`projects.preview_url` 不写入签名地址，预览地址每次请求按对象键即时解析。
- 2026-09-23 可靠性加固：配额改为条件原子扣减并在模型失败时退款，阶段执行增加原子抢占与 `600` 秒陈旧阶段回收，AI 与对象存储慢调用前后均不持有数据库事务。
- 2026-09-23 认证链路回归修复：平台登出回跳地址 `/logout-callback` 此前未注册路由，登出后会落到空白页，现补上该页面并统一为登出后自动返回首页。
- 2026-09-23 清理无引用的关键词模拟预览组件（`MiniApp.tsx` 及 `LoadingSpinner` 仅剩的登出页引用一并替换），仓库内不再残留模拟流程。
- 2026-09-23 验证通过：`verify_stage3.py`（上传 `200`、回读成功、预览地址 `200`、`Content-Type: text/html; charset=utf-8`、无 `X-Frame-Options`/CSP 阻断）、`verify_pipeline.py`（最终状态 `succeeded`、结构校验 `5/5`、冒烟 `4/4`、覆盖率 `86%`、重试 `run_no` 递增且不重复扣额、配额 `20/20`）。
- 2026-09-23 后端 `py_compile` 通过（`PYCOMPILE_OK`），前端 `pnpm run lint && pnpm run build` 通过（退出码 0，预渲染 `/` 与 `/blog/`）。
- 2026-09-23 修复结构化输出截断缺陷：`generation_ai.py` 增加本地容错（尾随逗号清理 + 未闭合字符串/括号补全）与更严格的修复提示，方案规划输出上限提升至 `2600`；此前 `claude-opus-5` 输出被截断时一次模型修复仍可能失败并中断生成。
- 2026-09-23 真实 AI 与对象存储验证复跑通过：上传 `200`、回读 `ok: True`、公开地址 `reachable: True`、AI `parse/plan/code` 全部成功（`RESULT storage: True artifacts: True ai: True`）。
- 2026-09-23 **阻塞项**：`verify_pipeline.py` 复跑时 AI 钱包余额不足（`insufficient_ai_balance`，HTTP `403`），六阶段端到端复跑未能完成；该失败为外部额度问题，非代码缺陷。已验证 `create_project` 在模型不可用时调用 `refund_quota` 退还额度，用户额度不会被白扣，阶段失败会落库为可见失败态。待额度恢复后重跑 `verify_pipeline.py` 即可完成最终端到端确认。
- 2026-09-23 新增并跑通可靠性用例 `verify_quota_refund.py`：在真实模型失败（`PermissionDeniedError`，余额不足）路径下断言额度回到 `0/20`、残留项目 `0`、残留阶段任务 `0`（`RESULT quota refund: OK`）。即外部模型不可用时用户额度不会被白扣，也不会留下半成品项目；同时该结果反证本地容错修复后 `verify_stage3.py` 的真实 AI 链路已可用（同一环境下解析/规划/代码生成全部成功）。
- 2026-09-23 更新日志追加 `v0.7.0` 发布记录（`src/data/changelog.ts`）：账号入口、我的项目列表与详情、额度视图、顶栏账号区、登录后回跳聚焦、页脚登录入口移除与登出 500 修复；页面自动置顶并标记 LATEST，类型筛选计数与版本跳转随之更新（当前 33 条、7 个版本）。
- 2026-09-23 文档同步：`docs/plan.md` 修正阶段一占位页范围（更新日志与登录已替换为真实页面）并补充阶段二交付清单条目；`app/frontend/README.md` 增加发布记录维护约定；根 `README.md` 补充账号体验与最新发布记录；`.wiki.md` 覆盖 `v0.7.0` 发布内容与验证说明。
- 2026-09-23 更新日志补齐 `v0.8.0`（`src/data/changelog.ts`）：真实模型六阶段、对象存储 iframe 预览、创建接口后台异步、配额条件原子扣减与失败退款、阶段原子抢占与陈旧回收、慢调用前后拆分事务、结构化输出截断容错、预览地址即时解析、网关 502 修复与登出回跳路由补齐；同时补齐用户反馈缺失的登出回跳条目。`docs/changelog.md` 按数据源逐条同步（版本号、日期、标题、摘要、标签、条目与类型），当前共 8 个版本、43 条条目（新增 18 / 优化 15 / 修复 10）。引用最新版本号的 `README.md`、`docs/plan.md`、`docs/frontend.md`、`app/frontend/README.md`、`.wiki.md` 与上下文文件同步更新。
- 2026-09-23 更新日志核对通过：`/changelog` 页面实测渲染 `total: 43 · versions: 8 · latest: 2026-09-23`，`v0.8.0` 置顶并标记 `LATEST`，类型筛选计数（全部 43 / 新增 18 / 优化 15 / 修复 10）与右侧版本锚点（`v0.8.0`～`v0.1.0`）均正确；`docs/changelog.md` 与数据源逐条一致，无残留旧版本号或旧条目数描述。前端 `pnpm run lint && pnpm run build` 通过（退出码 0，预渲染 `/` 与 `/blog/`）。
- 2026-09-23 阶段四文档同步（纯文档轮次）：发布记录追加 `v0.9.0`（测试用例与执行闭环，5 新增 / 3 优化 / 2 修复），`docs/changelog.md` 按数据源逐条同步，累计 9 个版本、53 条条目（新增 23 / 优化 18 / 修复 12）。`docs/mission.md` 项目范围新增「测试层」行并把测试用例管理从「未落地」移出；`docs/plan.md` 实施计划把阶段四标记为已完成；`docs/frontend.md` 与 `app/frontend/README.md` 更新最新版本号、阶段四能力说明与后续阶段口径；根 `README.md` 补阶段四进度段、验证脚本与文档索引；`.wiki.md` 同步版本计数与文档清单。统一口径：用例通过与否由真实产物内容决定、不由模型判定；无产物项目拒绝生成与执行；删除项目同步清理测试数据。

- 2026-09-23 删除首页页脚角落与账号状态无关的硬编码「登录」入口（已登录时仍显示登录）；登出链路加固：后端 `/api/v1/auth/logout` 支持 GET/POST 且地址构造失败时降级不再抛 500，前端 `useAuthStatus.logout()` 在平台登出接口异常时兜底回到首页。

- 2026-09-23 **502 根因定位并修复**：`/api/v1/generation/projects` 的 502 并非模型调用内联所致（创建接口此前已改为仅落库），真实链路是「阶段执行在整个慢调用期间持有数据库连接 + 无服务器连接池只有 1 条」。`services/generation.py` 已把阶段执行拆为三段独立短事务：`_claim_next_stage`（短事务原子抢占并复制只读输入快照）→ `_run_stage_work`（模型/对象存储慢调用，全程不持有连接）→ `_finish_stage` / `_abort_stage`（短事务回写结果或失败，且仅在阶段仍为 `running` 时才写，避免覆盖已被回收的状态）。`core/database.py` 无服务器分支的连接池由 `pool_size=1 / max_overflow=0 / pool_timeout=5s` 调整为 `pool_size=5 / max_overflow=5 / pool_timeout=30s`（均可由 `DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_POOL_TIMEOUT` 覆盖）。`routers/generation.py` 三个写接口改为在等待工作器前归还请求连接，并用 `_snapshot_with_quota` 独立短会话读取最新快照与额度。
- 2026-09-23 网关级回归通过（`verify_gateway_timeout.py`）：创建 `201 / 2.90s`，轮询 `200 / 1.0~4.2s`，4 路并发轮询全部 `200`（`1.40s`），最慢请求 `4.12s`，远低于 `25s` 安全线与 Cloudflare 约 `100s` 时限；创建后项目确实落库、无 `5xx`、无 `QueuePool` 超时。
- 2026-09-23 同次回归中 AI 钱包仍为余额不足（`insufficient_ai_balance`，HTTP `403`）：阶段 `parsing` 落为可见失败，残留项目 `0`、`FINAL quota used: 0`，再次确认外部模型不可用时用户额度不被白扣、也不留半成品项目。六阶段完整端到端复跑仍需待额度恢复后进行。
- 2026-09-23 **生产启动隐患确认**：`app/start_app_v2.sh:871` 的后端启动命令仍带 `--reload`（本地开发用）。`--reload` 会在文件变更时重启工作进程，重启窗口内无上游、进程内后台工作器也会被中断，是生产环境 502 的另一个来源；生产部署需改用不带 `--reload` 的启动命令。
- 2026-09-22 认证入口改造：新增 `/signup` 注册入口页（`src/pages/SignUp.tsx`），未登录点击「免费开始」改为进入注册页；顶栏按账号态切换，已登录显示账号邮箱与「退出登录」按钮（调用 `client.auth.logout()`），未登录显示「登录 + 免费开始」。
- 2026-09-22 完成前端模板初始化与暗色工程风设计系统（tokens、网格背景、焦点环、reduced-motion）。
- 2026-09-22 完成首屏 Prompt Console、预设提示胶囊与关键词匹配预设方案逻辑。
- 2026-09-22 完成三类迷你应用（看板 / 落地页 / 待办）真实组件渲染。
- 2026-09-22 完成能力介绍、模板库与分类筛选、定价区块、CTA 与页脚。
- 2026-09-22 完成 `/templates/:id`、`/docs`、`/changelog`、`/signin`、`/billing` 占位路由。
- 2026-09-22 对齐 `docs/plan.md` 六阶段流水线：新增「测试验证」步骤与生成完成后的测试报告面板。
- 2026-09-22 `pnpm run lint && pnpm run build` 通过（退出码 0）。
- 2026-09-22 同步文档至阶段一交付状态：`docs/mission.md` 范围表、`docs/plan.md` 实施计划与阶段一交付清单、根 `README.md` 与 `app/frontend/README.md`。
- 2026-09-22 将 `/changelog` 从占位页替换为真实更新日志页：新增 `src/data/changelog.ts` 发布记录与 `src/pages/Changelog.tsx`（类型筛选、版本锚点跳转、时间线）。
- 2026-09-22 激活 Atoms Cloud 后端，创建 `projects`、`build_tasks`、`project_versions`、`usage_quotas` 四张表，并生成对应 ORM、服务与实体 CRUD 路由。
- 2026-09-22 新增 `services/generation.py` 与 `routers/generation.py`：需求方案推导、六阶段任务推进、版本记录、按周期配额校验与扣减、失败停在失败阶段、重试开启新一批任务，全部按用户隔离。
- 2026-09-22 阶段二不产出真实部署地址（`preview_url` 为空），预览链接留待阶段三接入真实模型生成。
- 2026-09-22 前端接入 Atoms 账号三态：`client.auth.me()` 判定 loading/authenticated/anonymous，`client.auth.toLogin()` 发起登录，`/signin` 由占位页替换为真实登录入口。
- 2026-09-22 新增「我的项目」列表页与项目详情页，覆盖加载、未登录、空列表、失败重试与成功列表状态，并支持删除与失败重试。
- 2026-09-22 首页生成链路由本地定时状态机替换为 `POST /api/v1/generation/projects` + 轮询项目详情，时间线与测试报告均来自服务端持久化状态。
- 2026-09-22 后端 Python 语法检查通过；`pnpm run lint && pnpm run build` 通过（退出码 0）。
- 2026-09-22 统一前端认证上下文：`AuthContext` 改为复用 `useAuthStatus`（数据源唯一为 `client.auth.*`），遗留 Axios 认证工具链已从仓库移除且无任何引用（全文仅剩一处注释提及）。
- 2026-09-22 接口层复用：页面直接使用 `useAuthStatus` 与 `useProjects`，认证与项目查询共用同一 SDK 客户端实例 `src/lib/api.ts`。
- 2026-09-22 文档同步至阶段二：`app/frontend/README.md` 重写为阶段二状态（路由表、关键文件、生成链路、后续阶段），`.wiki.md` 更新模块清单、目录树、技术栈与使用说明。
- 2026-09-22 界面渲染验证通过（渲染检查无错误，风格与产品定位一致），阶段二交付完成。
- 2026-09-22 「免费开始」入口由失效的首页锚点改为真实链路：新增 `lib/startFree.ts`（跨页面意图）、`hooks/useStartFree.ts`（三态与登录判断）、`components/StartFreeIntentWatcher.tsx`（路由级兜底消费），未登录先进入登录页，登录后回到首页需求输入区并聚焦。
- 2026-09-22 免费额度侧未改动：每账号按自然月自动创建 20 次配额，跨月重置，额度用尽返回明确提示。
- 2026-09-22 `pnpm run lint && pnpm run build` 通过（退出码 0），界面渲染检查通过。
- 2026-09-23 文档统一同步（本轮）：以实际代码为准，逐份校正 `docs/mission.md`（各层落地状态与未落地范围）、`docs/plan.md`（阶段状态模型、六张表字段、模块划分与依赖方向、六阶段真实产出与失败处理、阶段三交付清单、未完成事项）、根 `README.md`（阶段三进度、后端运行与验证命令）、`app/frontend/README.md`（路由表补 `/logout-callback`、关键文件替换已删除的模拟预览组件、生成链路改为后台异步 + iframe 预览、移除阶段三待接入表述）、`.wiki.md`（目录树修正误列的后台工作器路径）与 `.atoms/ARCHITECTURE.md`（系统概览、文件树改为真实结构）。统一口径：预览地址按对象键即时解析、不落库；阶段状态取值为 `pending/running/done/failed`；项目状态取值为 `queued/pending/running/succeeded/failed`。

- 2026-09-23 文档同步收尾：清除文档内最后残留的过期表述（`.atoms/ARCHITECTURE.md` 文件树中已删除的模拟预览组件、`.wiki.md` 目录树中误列为后端根文件的后台工作器、`.atoms/PROGRESS.md` 中「可访问地址写入 `projects.preview_url`」的旧描述），并修正 `services/generation_artifacts.py` 模块与函数注释为真实行为（业务表只存对象键 `artifact_key`，访问地址按对象键即时解析、不落库）；注释改动后 `python -m py_compile services/generation_artifacts.py` 通过（`PYCOMPILE_OK`）。决策表中「阶段二 `preview_url` 留空」「阶段一用本地定时状态机」等历史行按约定保留原文，不改写历史，现状统一由概览段与新增决策行表达。

- 2026-09-23 新增后端开发文档 `docs/backend.md`：逐项对齐实际实现，覆盖技术栈与运行形态、目录职责与路由自动发现、生命周期与本地自测、全部环境变量、OIDC+PKCE 登录链路与应用 JWT 鉴权、数据库连接池策略与事务边界硬性规范、六张表数据模型、六阶段流水线与三段式阶段执行/后台工作器/配额退款/重试/测试报告口径、全量 API 清单（生成、认证、用户、实体 CRUD、AI、对象存储、管理健康）、AI 调用约定（模型、180 秒硬超时、异常收敛、JSON 容错）、对象存储产物链路、502/524 根因与修复对照表、幂等恢复、验证脚本清单与开发规范要点；根 `README.md` 目录规划与文档索引同步加入该文档。

- 2026-09-23 文档归档完成（本轮，纯文档轮次不做构建）：新增 `docs/frontend.md`，以实际代码为准逐项对齐前端技术栈、`App.tsx` 路由表、博客构建期预渲染（`/blog/*` 的 SPA 路由有意注释、`prerender/blog.js` 渲染、原生 `<a>` 跳转）、关键文件清单、生成链路七步、`src/lib/projects.ts` 六个接口契约与 `PIPELINE_TIMEOUT_MS = 60_000`、轮询间隔 `1500ms` 与网关瞬时错误分类/指数退避上限 `4` 次、认证三态与登出降级、视觉与工程约定（`DESIGN.md`、`AuthCallback.tsx` 只读、`data-mgx-overview`）、`vite.config.ts` 的代理与分包/预渲染行为、命令与验收要求；新增 `docs/changelog.md`，完整保留 `v0.7.0`～`v0.1.0` 共 7 个版本 33 条变更（版本、日期、标题、摘要、标签、类型条目），并明确该文档是平台发布记录、与用户生成项目的版本历史（`project_versions` / `GET /projects/{id}/versions`）是两个不同对象。同步位置：根 `README.md` 目录规划与文档索引新增两份文档，并标注 `app/frontend/README.md` 降为简明入口、完整说明以 `docs/frontend.md` 为准；`.wiki.md` 目录树与文件清单新增两份文档；`.atoms/ARCHITECTURE.md` 文件树 `docs/` 行补齐。统一口径保持：预览地址按对象键即时解析、不落库；阶段状态 `pending/running/done/failed`；项目状态 `queued/pending/running/succeeded/failed`。
