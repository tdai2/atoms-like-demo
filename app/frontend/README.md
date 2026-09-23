# Atoms · AI 应用生成平台前端

本前端落地 `docs/mission.md` 与 `docs/plan.md`：

- **阶段一（纯前端演示版）**：访客在首屏用一句自然语言描述需求，即可看到「需求输入 → 六阶段生成流水线 → 可运行应用预览」的完整链路。
- **阶段二（已接入 Atoms Cloud）**：账号复用平台内置认证，项目 / 六阶段任务 / 版本 / 配额全部落库，生成链路改为「创建任务 + 轮询服务端状态」，登录用户可查看归属自己的项目列表与详情。

营销、模板与定价内容仍是本地静态数据；真实模型生成与真实部署地址属于阶段三。

## 页面与路由

| 路由 | 页面 | 状态 |
|------|------|------|
| `/` | 首页：需求输入台、生成时间线、预览窗、能力、模板库、定价、CTA | 已实现（生成走后端） |
| `/projects` | 我的项目：当前账号的项目列表、额度用量、删除 | 已实现 |
| `/projects/:id` | 项目详情：六阶段快照、方案、测试报告、版本、失败重试 | 已实现 |
| `/signin` | 登录入口，调起平台账号登录 | 已实现 |
| `/blog`、`/blog/:slug` | 博客索引与文章页，构建期预渲染 | 已实现 |
| `/auth/callback`、`/auth/error` | 认证回调与错误处理入口 | 已实现（只读） |
| `/changelog` | 更新日志：平台发布记录，按类型筛选与版本跳转 | 已实现 |
| `/templates/:id` | 模板详情 | 建设中说明页 |
| `/docs` | 文档中心 | 建设中说明页 |
| `/billing` | 订阅与计费 | 建设中说明页 |

未落地的能力以统一的「建设中」说明页呈现，不伪造成已完成的功能。

## 关键文件

| 文件 | 职责 |
|------|------|
| `src/pages/Index.tsx` | 首页与生成链路：输入台、服务端阶段轮询、预览窗、模板库、定价、CTA |
| `src/pages/Projects.tsx` | 我的项目列表：加载 / 未登录 / 空列表 / 失败重试 / 成功列表与额度 |
| `src/pages/ProjectDetail.tsx` | 项目详情：六阶段流水线快照、方案、测试报告、版本与重试 |
| `src/pages/SignIn.tsx` | 平台账号登录入口 |
| `src/lib/projects.ts` | 生成接口的类型定义、调用封装与错误处理 |
| `src/hooks/useProjects.ts` | 项目列表 / 详情查询、轮询、创建、重试、删除 |
| `src/hooks/useAuthStatus.ts` | 账号三态：`loading` / `authenticated` / `anonymous` |
| `src/contexts/AuthContext.tsx` | 账号上下文，统一走 `client.auth.*` |
| `src/lib/api.ts` | `@metagptx/web-sdk` 客户端实例，所有请求的唯一边界 |
| `src/components/MiniApp.tsx` | 三类迷你应用（增长看板 / 品牌落地页 / 团队待办）的真实 DOM 渲染 |
| `src/components/SiteHeader.tsx` | 粘性顶栏与移动端菜单（含「我的项目」入口） |
| `src/pages/Placeholder.tsx` | 未建设模块的统一说明页，模板详情复用 |
| `src/pages/Changelog.tsx` | 更新日志页：类型筛选、版本锚点跳转与发布记录时间线 |
| `src/data/site.ts` | 预设提示词、六阶段步骤、模板、能力、定价 |
| `src/data/changelog.ts` | 平台发布记录数据源，按版本倒序，仅含呈现所需字段 |
| `src/index.css` | 设计令牌、网格背景、动效与 `prefers-reduced-motion` 处理 |
| `DESIGN.md` | 视觉规范来源，实现须服从该文档 |

## 生成链路

1. 用户在首屏输入需求（或点击示例提示胶囊），按 ⌘/Ctrl + Enter 或「生成应用」运行；空输入时主按钮禁用。
2. 未登录时先跳转平台登录；已登录则调用 `POST /api/v1/generation/projects` 创建项目并占用本周期额度。
3. 服务端按任务创建时间推导六个阶段的推进：解析需求 → 生成方案 → 编写代码 → 构建校验 → 测试验证 → 发布预览。
4. 前端轮询 `GET /api/v1/generation/projects/{id}` 刷新时间线，四态呈现：待执行、进行中、已完成、失败。刷新页面不丢进度。
5. 生成成功后预览窗渲染对应迷你应用，并展示服务端返回的测试报告（单元用例、冒烟用例、语句覆盖率）。
6. 失败停在失败阶段，可在首页或项目详情页触发 `POST .../retry` 重试；重试开启新一批任务且不重复扣额度。额度用尽时给出明确提示。

阶段二不产出真实部署地址：`projects.preview_url` 留空，预览窗仍是本地组件渲染。

## 开发与验证

```bash
pnpm install
pnpm run dev      # 本地预览
pnpm run lint     # ESLint 检查
pnpm run build    # 生产构建，含 / 与 /blog/ 预渲染
```

## 工程约定

- 技术栈固定为 Vite + React + TypeScript + Tailwind CSS + shadcn/ui + react-router-dom + TanStack Query，UI 组件从 `@/components/ui` 引入，`@/` 别名指向 `src/`。
- 认证只使用平台账号体系（`client.auth.me()` / `toLogin()` / `logout()`），不新增第二套登录逻辑。
- 后端接口统一通过 `client.apiCall.invoke()` 调用，不在前端直连数据库或堆积 fetch 封装。
- 视觉以 `DESIGN.md` 为唯一规范：暗色为唯一主题，主色 `#C8F751` 占比不超过 10%，不使用蓝紫渐变。
- `index.html` 中的标题、描述与 logo 由概览系统通过 `data-mgx-overview` 标记管理，不手动修改。
- `src/pages/AuthCallback.tsx` 为平台只读文件，不做修改。

## 后续阶段

- 阶段三：接入真实模型生成，把关键词推导替换为 AI 调用，并为 `preview_url` 写入真实部署地址、预览窗切换为 iframe。
- 阶段四：对话式增量修改与版本回溯。
- 阶段五：测试用例生成、执行与历史记录。
- 阶段六：Bug 提交、记录与自动修复。
- 阶段七：自定义域名、团队协作与权限。
