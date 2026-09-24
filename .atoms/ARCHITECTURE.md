# Architecture Design

## System Overview

Atoms 风格 AI 应用生成平台：前端 SPA + Atoms Cloud 后端。核心链路：用户在首屏 Prompt Console 输入需求 → 后端校验、占用额度并落库项目、版本与六阶段任务 → 后台工作器按真实模型执行结果推进阶段 → 前端轮询项目详情 → 在预览窗用 iframe 加载对象存储中的真实产物，完成后展示服务端返回的测试报告。账号复用 Atoms 内置认证，项目、任务、版本与配额均按用户隔离持久化。

生成链路不依赖前端定时器：`POST /api/v1/generation/projects` 创建任务并占用额度后立即返回，`GET /api/v1/generation/projects/{id}` 轮询阶段状态，重试复用同一项目开启新一批任务且不重复扣额。

阶段三完成收尾：六个阶段全部改为真实 AI 调用（需求解析 `deepseek-v4-flash`，方案规划与代码编写 `claude-opus-5`），生成的单文件应用上传至对象存储 `generation-artifacts`，对象键为 `projects/{project_id}/v{version}/index.html`，预览窗改为真实 iframe。数据库只保存对象键 `artifact_key`，`projects.preview_url` 不写入签名地址，预览地址每次请求即时解析。

执行形态为后台异步：请求在调度工作器前先归还数据库连接，阶段执行拆为「短事务抢占 → 无连接慢调用 → 短事务回写」三段，慢调用全程不持有数据库事务，避免与并发轮询争抢连接池。

## Tech Stack

前端：Vite + React + TypeScript + Tailwind CSS + shadcn/ui + react-router-dom + lucide-react + TanStack Query（轮询与缓存）。
后端：Atoms Cloud（FastAPI + SQLAlchemy 2.0 AsyncSession + PostgreSQL）。账号复用平台内置认证，不自建第二套登录；营销与模板内容仍来自本地静态数据。

## Module Design
| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| 路由壳 | 首页与次级占位路由挂载 | src/App.tsx |
| 首页 | Prompt Console、生成时间线、能力、模板库、定价、CTA | src/pages/Index.tsx |
| 顶栏 | 粘性导航与移动端菜单 | src/components/SiteHeader.tsx |
| 真实预览 | iframe 加载对象存储产物，含加载/空地址/失败/重试状态 | src/pages/ProjectDetail.tsx, src/pages/Index.tsx |
| 真实模型生成 | 需求解析、方案规划、代码编写与 JSON 修复重试 | app/backend/services/generation_ai.py |
| 产物存储 | HTML 上传、回读校验、预览地址解析与可访问性检查 | app/backend/services/generation_artifacts.py |
| 占位页 | 未建设模块的统一提示，模板详情复用 | src/pages/Placeholder.tsx |
| 更新日志 | 平台发布记录与类型筛选、版本跳转 | src/pages/Changelog.tsx, src/data/changelog.ts |
| 静态数据 | 预设提示词、构建步骤、模板、能力、定价 | src/data/site.ts |
| 设计系统 | 颜色/字体/网格背景/动效 | src/index.css, DESIGN.md |
| 账号状态 | Atoms 账号三态判定与登录跳转 | src/hooks/useAuthStatus.ts, src/pages/SignIn.tsx |
| 项目数据 | 生成接口类型定义与调用封装 | src/lib/projects.ts |
| 项目状态管理 | 列表/流水线查询、轮询、创建、重试、删除 | src/hooks/useProjects.ts |
| 项目列表 | 加载/未登录/空列表/失败重试/成功列表与额度 | src/pages/Projects.tsx |
| 项目详情 | 流水线快照、方案、测试报告与失败重试 | src/pages/ProjectDetail.tsx |
| 生成编排 | 方案推导、六阶段推进、版本与配额 | app/backend/services/generation.py |
| 生成接口 | 创建/列表/详情/重试/删除/版本/模板方案 | app/backend/routers/generation.py |
| 实体 CRUD | 项目、任务、版本、配额的自动生成路由 | app/backend/routers/{projects,build_tasks,project_versions,usage_quotas}.py |

## Tech Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| 是否接入后端 | 是（Atoms Cloud） | 账号、项目归属与生成过程需要持久化与用户隔离 |
| 生成进度 | 服务端阶段状态 + 前端轮询 | 过程可查询、可恢复，刷新页面不丢进度 |
| 阶段推进方式 | 按真实阶段执行结果推进 | 阶段三由真实模型调用驱动，不再用本地定时器模拟 |
| 失败与重试 | 停在失败阶段，重试开启新一批任务 | 落实「失败不清空」，且重试不重复扣额度 |
| 预览窗形态 | iframe 加载对象存储产物 | 阶段三产出真实可访问应用，比组件渲染更可信 |
| 模板缩略图 | CSS 线框 | 避免无意义 AI 配图，保持工程风一致性 |
| 产物落库方式 | 只存对象键，预览地址即时解析 | 签名地址有有效期，持久化会导致链接过期失效 |
| 慢调用事务边界 | AI 与对象存储调用前后不持有数据库事务 | 避免长事务占用连接池，也保证阶段状态按真实结果落库 |
| 配额并发保护 | 条件原子更新扣减，失败退款 | 并发首次创建不超扣，模型失败不白扣用户额度 |
| 阶段并发抢占 | 原子抢占 + `600` 秒陈旧阶段回收 | 多端轮询不会重复执行同一阶段 |

## File Tree Plan

```
app/frontend/src/
  App.tsx                     # 路由壳（含 /logout-callback）
  blog-routes.tsx             # 博客路由，SPA 与预渲染共用
  index.css                   # 设计令牌与动效
  data/site.ts                # 提示词、模板、阶段、能力、定价
  data/changelog.ts           # 平台发布记录
  components/SiteHeader.tsx   # 粘性顶栏与账号区
  components/LoadingSpinner.tsx
  contexts/AuthContext.tsx
  hooks/useAuthStatus.ts
  hooks/useProjects.ts
  hooks/useStartFree.ts
  lib/api.ts                  # Web SDK 客户端唯一边界
  lib/projects.ts             # 生成接口封装与网关错误处理
  lib/startFree.ts
  pages/Index.tsx             # 首页与生成链路（轮询 + iframe 预览）
  pages/Projects.tsx
  pages/ProjectDetail.tsx
  pages/SignIn.tsx / SignUp.tsx / LogoutCallbackPage.tsx
  pages/AuthCallback.tsx / AuthError.tsx
  pages/Changelog.tsx / Placeholder.tsx
app/frontend/DESIGN.md

app/backend/
  main.py                     # FastAPI 入口、自动路由、恢复任务
  lambda_handler.py
  core/                       # 配置、数据库、认证、遥测
  dependencies/               # 认证与数据库依赖
  models/ schemas/ alembic/   # 持久化实体、契约与迁移
  routers/                    # generation / auth / aihub / storage / entities
  services/                   # generation, pipeline_runner, generation_ai, generation_artifacts, storage
  verify_*.py                 # stage3 / pipeline / quota_refund / gateway_timeout
docs/
  mission.md  plan.md  frontend.md  backend.md  changelog.md
```

## Implementation Guide

阶段三已完成：`services/generation.py` 的六个阶段由真实模型调用驱动（`services/generation_ai.py` 负责需求解析、方案规划、代码编写与 JSON 一次修复；`services/generation_artifacts.py` 负责上传、回读校验与预览地址解析），预览窗已切换为 iframe。`build_tasks` 的阶段状态机与配额契约保持不变，前端调用方式未改动。

后续迭代注意：新增阶段或修改结构化输出契约时，同步维护 `generation_ai.py` 的字段校验与 `docs/plan.md` 的状态模型；产物路径规则变更需同时更新 `artifact_key()` 与既有对象。
