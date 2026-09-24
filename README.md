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
│   ├── plan.md       # 工程方案：架构、模块、技术选型、实施阶段
│   ├── frontend.md   # 前端开发文档：技术栈、路由、关键文件、生成链路、认证、构建配置
│   ├── backend.md    # 后端开发文档：分层结构、认证、事务边界、流水线、API、存储、部署
│   └── changelog.md  # 平台发布记录：与 /changelog 页面同源的版本历史
├── app/
│   ├── frontend/     # 前端 SPA（输入台、时间线、预览窗、我的项目）
│   └── backend/      # Atoms Cloud 后端（认证、项目、任务、版本、配额、测试）
└── .atoms/           # 团队协作上下文：架构、决策与进度
```

## 当前进度

阶段一**纯前端演示版已完成**：需求输入台、六阶段生成时间线、应用预览窗（含测试报告）、模板库与定价均已落地。

阶段二**账号与项目持久化已完成**：Atoms Cloud 已激活，`projects`、`build_tasks`、`project_versions`、`usage_quotas` 四张表落库；生成链路改为 `POST /api/v1/generation/projects` 创建任务并轮询项目详情，阶段状态与测试报告由服务端持久化；前端接入 Atoms 账号三态，新增「我的项目」列表页与项目详情页，登录用户可查看、重试与删除自己的项目。`pnpm run lint` 与 `pnpm run build` 通过。

阶段二同时补齐了账号体验与发布记录：顶栏账号区在登录后显示账号邮箱与「退出登录」，未登录显示「登录 / 免费开始」；首页页脚不再出现与账号状态无关的登录入口；`/changelog` 目前共 9 个版本、53 条变更条目，最新为 `v0.9.0`（测试用例与执行闭环），上一版为 `v0.8.0`（真实生成与可访问产物）。

阶段三**真实生成与可访问产物已完成**：六个阶段全部由真实模型调用驱动（需求解析 `deepseek-v4-flash`，方案规划与代码编写 `claude-opus-5`），生成的单文件应用上传至对象存储 `generation-artifacts`，预览窗改为 iframe 加载真实产物地址。执行改为后台异步：创建接口只做校验、扣额与落库并立即返回，后台工作器推进阶段，前端轮询服务端状态，请求全程不持有数据库连接等待慢调用。

阶段三同时完成可靠性加固：配额改为条件原子扣减并在模型失败时退还，阶段执行拆为「短事务抢占 → 无连接慢调用 → 短事务回写」三段，阶段具备原子抢占与 `600` 秒陈旧回收，进程重启后会重新接管未完成项目。数据库只保存对象键 `artifact_key`，签名预览地址每次请求即时解析，不落库。

阶段四**测试用例与执行闭环已完成**：`test_cases`、`test_runs` 两张表按账号隔离建表，用例可由真实模型基于方案与对象存储中的真实产物生成（6-10 条），也可手动新增、编辑、启用 / 停用与删除；执行时回读当前产物源码做**确定性断言匹配**，产出总数、通过数、失败数、耗时与逐例结果，每次运行都落库形成可回溯的测试历史。项目详情页已接入测试面板，覆盖加载、无产物、无用例、执行失败与成功态；没有产物的项目会拒绝生成与执行，删除项目会同步清理其测试数据。

## 本地运行

```bash
# 前端
cd app/frontend
pnpm install
pnpm run dev      # 本地预览
pnpm run lint     # 代码检查
pnpm run build    # 生产构建（含 / 与 /blog/ 预渲染）

# 后端
cd app/backend
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8000   # 生产部署不要加 --reload
curl http://localhost:8000/health
```

后端的环境变量、认证、事务边界、API 契约与验证脚本见 [docs/backend.md](docs/backend.md)。

后端验证脚本（需要可用的平台 AI 额度）：

```bash
cd app/backend
python verify_stage3.py           # 真实 AI + 对象存储 + 预览可达性
python verify_pipeline.py         # 六阶段端到端
python verify_quota_refund.py     # 模型失败退款与无残留
python verify_gateway_timeout.py  # 创建/轮询耗时与并发
python verify_test_suite.py       # 阶段四：用例生成约束、执行统计、历史与隔离
```

## 文档

| 文档 | 内容 |
|------|------|
| [docs/mission.md](docs/mission.md) | 产品使命、原则、目标用户、项目范围、成功定义、不做什么 |
| [docs/plan.md](docs/plan.md) | 分层架构、状态模型、数据模型、模块划分、技术选型、实施阶段与阶段一交付清单 |
| [docs/frontend.md](docs/frontend.md) | 前端开发文档：技术栈、路由表与博客预渲染、关键文件、生成链路与接口契约、轮询与错误处理、认证、视觉与工程约定、构建配置 |
| [docs/backend.md](docs/backend.md) | 后端开发文档：目录结构、认证与授权、数据库与事务边界、六阶段生成流水线、测试能力、API 清单、AI 与对象存储、可靠性与部署约束 |
| [docs/changelog.md](docs/changelog.md) | 平台发布记录：`v0.9.0` 至 `v0.1.0` 的版本、日期、摘要、标签与变更条目 |
| [app/frontend/DESIGN.md](app/frontend/DESIGN.md) | 视觉规范：色彩令牌、字体、间距圆角、组件状态、动效与可访问性 |
| [app/frontend/README.md](app/frontend/README.md) | 前端简明入口：路由与关键文件速览，完整说明以 `docs/frontend.md` 为准 |

所有技术决策服从 `docs/mission.md` 的方向与边界。
