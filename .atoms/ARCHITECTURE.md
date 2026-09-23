# Architecture Design

## System Overview

Atoms 风格 AI 应用生成平台：前端 SPA + Atoms Cloud 后端。核心链路：用户在首屏 Prompt Console 输入需求 → 后端按需求文本推导结构化方案并落库项目、版本与六阶段任务 → 前端轮询项目详情，由服务端时间驱动阶段状态 → 在预览窗渲染对应的真实迷你应用组件，完成后展示服务端返回的测试报告。账号复用 Atoms 内置认证，项目、任务、版本与配额均按用户隔离持久化。

阶段二起生成链路不再依赖前端定时器：`POST /api/v1/generation/projects` 创建任务并占用额度，`GET /api/v1/generation/projects/{id}` 轮询阶段状态，重试复用同一项目开启新一批任务。真实模型生成与可访问的部署地址留待阶段三。

## Tech Stack

前端：Vite + React + TypeScript + Tailwind CSS + shadcn/ui + react-router-dom + lucide-react + TanStack Query（轮询与缓存）。
后端：Atoms Cloud（FastAPI + SQLAlchemy 2.0 AsyncSession + PostgreSQL）。账号复用平台内置认证，不自建第二套登录；营销与模板内容仍来自本地静态数据。

## Module Design
| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| 路由壳 | 首页与次级占位路由挂载 | src/App.tsx |
| 首页 | Prompt Console、生成时间线、能力、模板库、定价、CTA | src/pages/Index.tsx |
| 顶栏 | 粘性导航与移动端菜单 | src/components/SiteHeader.tsx |
| 预览应用 | 三种迷你应用（看板/落地页/待办）真实 DOM 渲染 | src/components/MiniApp.tsx |
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
| 生成动画 | 服务端阶段状态 + 前端轮询 | 过程可查询、可恢复，刷新页面不丢进度 |
| 阶段推进方式 | 按任务创建时间推导 | 阶段二不引入队列与外部调用，保持事务简单 |
| 失败与重试 | 停在失败阶段，重试开启新一批任务 | 落实「失败不清空」，且重试不重复扣额度 |
| 预览窗形态 | 真实组件渲染 | 比截图更可信，也便于后续接真实生成结果 |
| 模板缩略图 | CSS 线框 | 避免无意义 AI 配图，保持工程风一致性 |

## File Tree Plan

```
src/
  App.tsx
  index.css
  data/site.ts
  components/SiteHeader.tsx
  components/MiniApp.tsx
  pages/Index.tsx
  pages/Changelog.tsx
  pages/Placeholder.tsx
  data/changelog.ts
DESIGN.md
```

## Implementation Guide

阶段三接入真实模型生成时：在 `services/generation.py` 中把基于关键词的方案推导与阶段日志替换为 AI 调用（方案与代码生成用 `claude-opus-5`，需求解析用 `deepseek-v4-flash`），为 `projects.preview_url` 写入真实部署地址，并将预览窗由 `MiniApp` 组件切换为 iframe。`build_tasks` 的阶段状态机与配额校验保持现有契约不变，前端无需改动调用方式。
