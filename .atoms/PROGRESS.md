---
last_updated: 2026-09-22T07:20:00Z
---

# Requirements & Progress

## Requirements Overview

依据 `docs/mission.md` 与 `docs/plan.md` 落地阶段一：Atoms 风格 AI 应用生成平台的**纯前端演示版**。目标是在三十秒内让用户理解「一句话 → 生成可运行应用」的产品主张，并看到完整演示链路。

阶段二在此之上接入 Atoms Cloud：账号复用平台内置认证，项目、六阶段任务、版本与配额落库，生成链路改为「创建任务 + 轮询服务端状态」。交付目标是登录用户能看到归属自己的项目列表。

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

## Progress Log

- 2026-09-23 阶段三收尾完成：六个阶段由真实 AI 驱动（需求解析 `deepseek-v4-flash`、方案规划与代码编写 `claude-opus-5`），生成的单文件应用上传至对象存储 `generation-artifacts`（键 `projects/{id}/v{n}/index.html`），可访问地址写入 `projects.preview_url`，预览窗改为真实 iframe；数据库只存 `artifact_key`，签名地址即时解析不持久化。
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

- 2026-09-23 删除首页页脚角落与账号状态无关的硬编码「登录」入口（已登录时仍显示登录）；登出链路加固：后端 `/api/v1/auth/logout` 支持 GET/POST 且地址构造失败时降级不再抛 500，前端 `useAuthStatus.logout()` 在平台登出接口异常时兜底回到首页。

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
