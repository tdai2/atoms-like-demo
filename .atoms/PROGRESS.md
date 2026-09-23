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

## Progress Log

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
