# Atoms · AI 应用生成平台

让任何有想法的人，用一句自然语言描述，就能得到一个真正能运行、能分享、能持续迭代的应用。

生成的终点不是代码，而是一个活着的应用。

## 核心流水线

```
用户意图 → 需求解析 → 方案规划 → 代码生成 → 构建校验 → 测试验证 → 发布预览 → 可访问的应用
              ↑                                                              │
              └──────────────── 对话式增量修改 ←─────────────────────────────┘
```

每个阶段独立、可查询、可观测。失败不清空，停在失败阶段暴露原因——过程透明优于结果惊喜。

## 产品原则

1. 端到端，不留半成品
2. 过程透明优于结果惊喜
3. 增量胜过重写
4. 默认就很好看
5. 用户始终拥有出口
6. 克制胜过堆砌

## 技术栈

| 层 | 选型 |
|----|------|
| 前端 | React + TypeScript · Vite · Tailwind · shadcn/ui · lucide-react |
| 后端 | Python FastAPI · Atoms Cloud Edge Functions |
| 数据 | PostgreSQL（关系）+ Atoms 对象存储（产物与资源） |
| 模型 | `claude-opus-5` 负责方案与代码生成，`deepseek-v4-flash` 负责需求解析 |

## 目录规划

```
atoms_demo/
├── docs/
│   ├── mission.md    # 顶层纲领：使命、原则、边界、范围
│   └── plan.md       # 工程方案：架构、模块、技术选型、实施阶段
├── app/
│   ├── frontend/     # 前端 SPA（输入台、时间线、预览窗、我的项目）
│   └── backend/      # Atoms Cloud 后端（认证、项目、任务、版本、配额）
└── .atoms/           # 团队协作上下文：架构、决策与进度
```

## 当前进度

阶段一**纯前端演示版已完成**：需求输入台、六阶段生成时间线、应用预览窗（含测试报告）、模板库与定价均已落地。

阶段二**账号与项目持久化已完成**：Atoms Cloud 已激活，`projects`、`build_tasks`、`project_versions`、`usage_quotas` 四张表落库；生成链路改为 `POST /api/v1/generation/projects` 创建任务并轮询项目详情，阶段状态与测试报告由服务端持久化；前端接入 Atoms 账号三态，新增「我的项目」列表页与项目详情页，登录用户可查看、重试与删除自己的项目。`pnpm run lint` 与 `pnpm run build` 通过。

阶段二同时补齐了账号体验与发布记录：顶栏账号区在登录后显示账号邮箱与「退出登录」，未登录显示「登录 / 免费开始」；首页页脚不再出现与账号状态无关的登录入口；`/changelog` 最新条目为 `v0.7.0`（账号体系与项目持久化）。

真实模型生成与可访问的部署链接属于阶段三，尚未接入：当前方案推导与阶段日志由后端按需求关键词与时间推导，阶段二不产出真实部署地址（`preview_url` 为空）。

## 本地运行

```bash
cd app/frontend
pnpm install
pnpm run dev      # 本地预览
pnpm run lint     # 代码检查
pnpm run build    # 生产构建（含 / 与 /blog/ 预渲染）
```

## 文档

| 文档 | 内容 |
|------|------|
| [docs/mission.md](docs/mission.md) | 产品使命、原则、目标用户、项目范围、成功定义、不做什么 |
| [docs/plan.md](docs/plan.md) | 分层架构、状态模型、数据模型、模块划分、技术选型、实施阶段与阶段一交付清单 |
| [app/frontend/DESIGN.md](app/frontend/DESIGN.md) | 视觉规范：色彩令牌、字体、间距圆角、组件状态、动效与可访问性 |
| [app/frontend/README.md](app/frontend/README.md) | 前端路由、关键文件、生成演示链路与开发说明 |

所有技术决策服从 `docs/mission.md` 的方向与边界。
