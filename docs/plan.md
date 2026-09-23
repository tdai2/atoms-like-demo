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
| 解析需求 | `parsing` | 结构化需求（实体、页面、交互） | 需求过于模糊时回问用户 |
| 生成方案 | `planning` | 技术栈选型 + 组件树 | 降级到最接近的模板方案 |
| 编写代码 | `coding` | 文件集合（路径 → 内容） | 记录失败文件，保留已生成部分 |
| 构建校验 | `building` | 构建日志 + 产物 | 回灌错误信息触发一次自动修复 |
| 测试验证 | `testing` | 测试报告（单元/冒烟） | 定位失败用例并回灌到代码生成阶段 |
| 发布预览 | `deploying` | 预览 URL | 保留上一个可用版本 |

失败不清空任务，而是停在失败阶段并暴露原因——对应 `mission.md` 的「过程透明优于结果惊喜」。

### 1.4 数据模型草案

| 表 | 关键字段 | 说明 |
|----|---------|------|
| `projects` | `id` `user_id` `name` `prompt` `status` `preview_url` | 一个用户项目 |
| `project_versions` | `id` `project_id` `version` `diff_summary` `files_key` | 版本链，支持回溯 |
| `build_tasks` | `id` `project_id` `stage` `state` `log` `error` | 驱动生成时间线 |
| `templates` | `id` `name` `category` `schema` | 模板库，可被项目引用为起点 |
| `usage_quotas` | `user_id` `period` `used` `limit` | 按套餐限制生成次数 |

文件产物不入库，存对象存储，库中只保留引用键。

## 二、模块划分

### 2.1 前端模块（`app/frontend`，阶段一已落地）

| 模块 | 职责 | 关键文件 |
|------|------|---------|
| 路由壳 | 首页与次级页面路由挂载 | `src/App.tsx` |
| 首页 | 输入台、时间线、能力、模板库、定价、CTA | `src/pages/Index.tsx` |
| 顶栏 | 粘性导航与移动端菜单 | `src/components/SiteHeader.tsx` |
| 预览渲染 | 三类迷你应用的真实 DOM 渲染 | `src/components/MiniApp.tsx` |
| 占位页 | 未建设模块的统一说明，模板详情复用 | `src/pages/Placeholder.tsx` |
| 静态数据 | 预设提示词、构建步骤、模板、能力、定价 | `src/data/site.ts` |
| 设计系统 | 颜色、字体、网格背景、动效 | `src/index.css` `DESIGN.md` |

### 2.2 后端模块（阶段二已落地）

| 模块 | 职责 | 对外接口 |
|------|------|---------|
| 鉴权 | 会话校验与用户身份解析 | 复用 Atoms 内置账号体系（`dependencies/auth.py`），不自建 |
| 项目管理 | 项目增删改查、版本列表与回溯 | `GET/POST /api/v1/generation/projects`、`/projects/{id}/versions`、`DELETE /projects/{id}` |
| 生成编排 | 创建生成任务、推进阶段、写入状态 | `POST /api/v1/generation/projects`、`GET /api/v1/generation/projects/{id}`、`POST /projects/{id}/retry` |
| 方案推导 | 由需求文本推导页面、实体与技术栈 | `GET /api/v1/generation/templates/{key}`；阶段三替换为 AI 网关 |
| 实体 CRUD | 四张表的自动生成路由，均按用户隔离 | `/api/v1/entities/{projects,build_tasks,project_versions,usage_quotas}` |
| 产物存储 | 生成文件的读写与预览资源托管 | 阶段三接入；当前版本记录只保存对象存储引用键 |
| 配额 | 按套餐校验与计数 | `services/generation.py` 的 `get_or_create_quota`，创建任务前校验并扣减 |

### 2.3 模块依赖方向

```
体验层 → 接口层 → { 鉴权, 项目管理, 生成编排 }
                      生成编排 → AI 网关 → 模型
                      生成编排 → 产物存储
                      生成编排 → 配额
```

依赖单向向下，禁止反向调用；AI 网关只被生成编排使用，保证模型替换不外溢。

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
| 预览窗形态 | 当前真实组件渲染，接入后改 iframe | 演示形态下更可信，接入后自然过渡到真实部署 |
| 模板缩略图 | CSS 线框 | 避免无意义配图，保持工程风一致 |
| 生成推进方式 | 阶段一为定时状态机，阶段二起改为服务端阶段状态 + 前端轮询 | 演示期无需后端；接入后过程可查询、刷新不丢失 |
| 是否自建管理后台登录 | 否 | 用账号角色区分权限，不做第二套认证 |
| 产物是否入库 | 否，存对象存储 | 避免大字段拖垮数据库性能 |

## 四、实施计划

| 阶段 | 范围 | 交付标志                      |
|------|------|---------------------------|
| 一（已完成） | 纯前端演示：输入台、时间线、预览窗、模板库、定价 | 三十秒内理解产品主张                |
| 二（已完成） | 激活后端，落地账号、项目表、生成接口 | 登录后能看到自己的项目列表             |
| 三 | 接入真实模型生成，替换预设匹配 | 输入任意需求产出可访问链接             |
| 四 | 对话式增量修改、版本回溯 | 追加需求只改动对应部分               |
| 五 | 测试用例生成、执行与结果记录 | 可以自动或手动生成测试用例，执行并查询历史测试记录 |
| 六 | Bug 提交、记录与自动修复 | 能提交 bug、记录 bug，并尝试自行解决    |
| 七 | 自定义域名、团队协作与权限 | 项目可对外正式发布                 |

### 阶段一交付清单

| 交付项 | 落地位置 |
|--------|---------|
| 需求输入台（预设胶囊、⌘/Ctrl + Enter、空输入禁用态） | `app/frontend/src/pages/Index.tsx` |
| 六阶段生成时间线与定时推进状态机 | `app/frontend/src/pages/Index.tsx`、`src/data/site.ts` |
| 应用预览窗与测试报告面板 | `src/components/MiniApp.tsx`、`src/data/site.ts` |
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
| 更新日志页与发布记录数据源（最新 `v0.7.0` 覆盖账号与项目持久化） | `src/pages/Changelog.tsx`、`src/data/changelog.ts` |
| 顶栏账号区（登录 / 免费开始 / 账号邮箱 / 退出登录）与登出降级 | `src/components/SiteHeader.tsx`、`src/hooks/useAuthStatus.ts`、`app/backend/routers/auth.py` |

验证方式：后端 Python 语法检查通过；`pnpm run lint` 与 `pnpm run build` 通过。

阶段二不产出真实部署地址：`projects.preview_url` 保持为空，预览窗仍由 `MiniApp` 组件渲染，避免出现假的可访问链接。

### 阶段三迁移要点

1. `services/generation.py` 中基于关键词的 `build_spec` 与 `stage_output` 替换为 AI 调用（方案与代码生成用 `claude-opus-5`，需求解析用 `deepseek-v4-flash`）。
2. 阶段推进由「按创建时间推导」改为真实执行结果驱动，`build_tasks` 的状态契约保持不变。
3. `projects.preview_url` 写入真实部署地址，预览窗由 `MiniApp` 组件切换为 iframe。
4. 产物写入对象存储，`project_versions.files_key` 指向真实产物。

生成接口与配额校验的契约不变，前端无需改动调用方式。