# Frontend — 前端开发文档

> 本文档描述 `app/frontend` 的**实际实现**，与代码逐项对齐。
> 方向与边界服从 `docs/mission.md`，工程方案服从 `docs/plan.md`，视觉规范服从 `app/frontend/DESIGN.md`。
> 平台模板自带的开发规范仍在 `app/frontend/README.md`（简明入口）；本文档是前端实现说明的完整事实来源。

## 一、技术栈与工程形态

| 层 | 选型 |
|----|------|
| 构建 | Vite 5 + TypeScript 5 + SWC（`@vitejs/plugin-react-swc`） |
| 框架 | React 18 + `react-router-dom` 6（SPA） |
| 样式 | Tailwind CSS + shadcn/ui（Radix UI）+ `lucide-react` |
| 数据 | `@tanstack/react-query`（查询、缓存与轮询）+ `@metagptx/web-sdk`（认证与接口调用） |
| 内容 | `markdown-to-jsx` + `yaml`（博客 Markdown 与 frontmatter） |
| 质量 | ESLint 9 + `typescript-eslint` |

`@/` 别名指向 `src/`（见 `vite.config.ts` 的 `resolve.alias`）。UI 组件统一从 `@/components/ui` 引入。

## 二、页面与路由

路由表以 `src/App.tsx` 的 `<Routes>` 为准：

| 路由 | 页面组件 | 状态 |
|------|---------|------|
| `/` | `pages/Index.tsx` | 已实现：需求输入台、六阶段时间线、iframe 预览窗、能力、模板库、定价、CTA |
| `/projects` | `pages/Projects.tsx` | 已实现：当前账号项目列表、额度用量、删除 |
| `/projects/:id` | `pages/ProjectDetail.tsx` | 已实现：六阶段快照、方案、测试报告、版本、失败重试 |
| `/signin` | `pages/SignIn.tsx` | 已实现：调起平台账号登录 |
| `/signup` | `pages/SignUp.tsx` | 已实现：注册入口，调起平台账号页完成注册 |
| `/auth/callback` | `pages/AuthCallback.tsx` | 平台只读文件，不修改 |
| `/auth/error` | `pages/AuthError.tsx` | 已实现：认证错误说明 |
| `/logout-callback` | `pages/LogoutCallbackPage.tsx` | 已实现：平台登出回跳落点，自动返回首页 |
| `/changelog` | `pages/Changelog.tsx` | 已实现：发布记录、类型筛选、版本锚点跳转 |
| `/templates/:id` | `pages/Placeholder.tsx` | 建设中说明页（复用同一个占位组件） |
| `/docs` | `pages/Placeholder.tsx` | 建设中说明页 |
| `/billing` | `pages/Placeholder.tsx` | 建设中说明页 |
| `/blog/*` | `blog-routes.tsx` | **不在 SPA 路由中**，见下节 |

未落地的次级页面统一使用「建设中」说明页，不伪造成已完成的功能——对应 `mission.md` 原则 1 与原则 2。

### 博客：构建期预渲染，而非 SPA 路由

- `src/App.tsx` 中 `/blog/*` 的 SPA 路由被**有意注释**，`/blog/` 与 `/blog/:slug/` 由 `vite-prerender-plugin` 在**构建期**渲染为静态页面。
- 预渲染入口为 `prerender/blog.js`，渲染组件复用 `src/blog-routes.tsx`（`index` / `:slug` / 未匹配回退到 `/blog/`）。
- 文章内容来自 `seo/content/**/*.md`，由 `src/lib/blog.ts` 以 `import.meta.glob` 编译期收集，解析 frontmatter 后生成标题、描述、Open Graph 与 Twitter Card 元信息。
- `/blog/`、`/blog/:slug/` 是**静态页面**，因此站内跳转必须使用原生 `<a href="/blog/">`，不能使用 `react-router` 的 `<Link>`。

## 三、关键文件

| 文件 | 职责 |
|------|------|
| `src/pages/Index.tsx` | 首页与生成链路：输入台、服务端阶段轮询、iframe 预览窗、模板库、定价、CTA |
| `src/pages/Projects.tsx` | 我的项目列表：加载 / 未登录 / 空列表 / 失败重试 / 成功列表与额度 |
| `src/pages/ProjectDetail.tsx` | 项目详情：六阶段流水线快照、方案、测试报告、版本、重试与测试面板入口 |
| `src/components/TestSuitePanel.tsx` | 阶段四测试面板：用例生成与手动增删改、执行、结果统计与运行历史切换 |
| `src/pages/Changelog.tsx` | 更新日志页：类型筛选计数、版本锚点、发布记录时间线、`LATEST` 标记 |
| `src/pages/Placeholder.tsx` | 未建设模块的统一说明页，模板详情复用 |
| `src/pages/SignIn.tsx`、`src/pages/SignUp.tsx` | 平台账号登录与注册入口 |
| `src/pages/LogoutCallbackPage.tsx` | 登出完成页，处理平台登出后的回跳落点 |
| `src/lib/api.ts` | `@metagptx/web-sdk` 客户端实例，所有请求的唯一边界 |
| `src/lib/projects.ts` | 生成接口的类型定义、调用封装、超时与网关错误分类 |
| `src/lib/startFree.ts` | 「免费开始」意图的保存、读取与消费，以及输入框聚焦事件 |
| `src/lib/blog.ts` | 博客 Markdown 收集、frontmatter 解析与 SEO 元信息推导 |
| `src/hooks/useProjects.ts` | 项目列表 / 详情的查询、轮询、创建、重试、删除 |
| `src/hooks/useAuthStatus.ts` | 账号三态：`loading` / `authenticated` / `anonymous`，含登录与登出 |
| `src/contexts/AuthContext.tsx` | 账号上下文，与 `useAuthStatus` 同源，统一走 `client.auth.*` |
| `src/components/SiteHeader.tsx` | 粘性顶栏与移动端菜单，含「我的项目」入口与账号区 |
| `src/components/StartFreeIntentWatcher.tsx` | 路由级兜底：登录后消费意图并回到首页输入区 |
| `src/components/LoadingSpinner.tsx` | 统一加载态组件 |
| `src/blog-routes.tsx` | 博客路由定义，SPA 与预渲染共用 |
| `src/data/site.ts` | 预设提示词、六阶段步骤、模板、能力与定价 |
| `src/data/changelog.ts` | 平台发布记录数据源（详见 `docs/changelog.md`） |
| `src/index.css`、`src/App.css` | 设计令牌、网格背景、动效与组件样式 |
| `DESIGN.md` | 视觉规范来源，实现须服从该文档 |

## 四、生成链路

1. 用户在首屏输入需求（或点击示例提示胶囊），按 ⌘/Ctrl + Enter 或「生成应用」运行；空输入时主按钮禁用。
2. 未登录时先跳转平台账号页；已登录则调用 `POST /api/v1/generation/projects` 创建项目并占用本周期额度。
3. 创建请求只做校验、占用额度并落库项目，随即调度后台工作器并立即返回，**不在请求内等待模型调用**。
4. 后台工作器按真实执行结果推进六个阶段：解析需求 → 生成方案 → 编写代码 → 构建校验 → 测试验证 → 发布预览；失败时停在失败阶段并写入可读原因。
5. 前端轮询 `GET /api/v1/generation/projects/{id}` 刷新时间线，四态呈现：待执行 / 进行中 / 已完成 / 失败。刷新页面不丢进度。
6. 生成成功后预览窗用 **iframe** 加载对象存储产物的真实可访问地址，并展示服务端返回的测试报告（单元用例、冒烟用例、语句覆盖率）。
7. 失败可在首页或项目详情页触发 `POST /api/v1/generation/projects/{id}/retry`；重试开启新一批任务且不重复扣额度。额度用尽时给出明确提示。

预览地址由服务端按对象键即时解析，**不落库**；模型或存储不可用时接口返回可读错误并退还额度，前端按错误类型展示提示而非静默失败。

### 接口契约（`src/lib/projects.ts`）

| 函数 | 方法 | 路径 |
|------|------|------|
| `fetchProjects()` | `GET` | `/api/v1/generation/projects` |
| `createProject(prompt, templateKey)` | `POST` | `/api/v1/generation/projects` |
| `fetchPipeline(id)` | `GET` | `/api/v1/generation/projects/{id}` |
| `retryProject(id)` | `POST` | `/api/v1/generation/projects/{id}/retry` |
| `fetchVersions(id)` | `GET` | `/api/v1/generation/projects/{id}/versions` |
| `deleteProject(id)` | `DELETE` | `/api/v1/generation/projects/{id}` |
| `fetchTestSuite(id)` | `GET` | `/api/v1/testing/projects/{id}/suite` |
| `generateTestCases(id)` | `POST` | `/api/v1/testing/projects/{id}/cases/generate` |
| `createTestCase(id, payload)` | `POST` | `/api/v1/testing/projects/{id}/cases` |
| `updateTestCase(caseId, payload)` | `PUT` | `/api/v1/testing/cases/{caseId}` |
| `deleteTestCase(caseId)` | `DELETE` | `/api/v1/testing/cases/{caseId}` |
| `runTestSuite(id)` | `POST` | `/api/v1/testing/projects/{id}/runs` |
| `fetchTestRun(runId)` | `GET` | `/api/v1/testing/runs/{runId}` |

所有请求通过 `client.apiCall.invoke()` 发出，不在前端直连数据库或另建 fetch 封装。
生成类请求超时为 `PIPELINE_TIMEOUT_MS = 60_000`；列表、版本与删除使用 SDK 默认超时。

### 轮询与错误处理（`src/hooks/useProjects.ts`、`src/lib/projects.ts`）

- 轮询间隔 `POLL_INTERVAL_MS = 1500`，当项目状态不是 `queued` / `running`（即进入终态）时停止轮询。
- 网关瞬时故障（`408` / `429` / `502` / `503` / `504`，或网络层 `network error` / `timeout` / `failed to fetch` / `ECONNRESET` / `socket hang up`）由 `isTransientGatewayError()` 判定为可重试。
- 可重试错误按指数退避重试：`min(1000 × 2^attemptIndex, 8000)` 毫秒，最多 `PIPELINE_RETRY_LIMIT = 4` 次；其余错误立即暴露给用户，避免把真实业务失败拖成等待。
- 创建、重试、删除成功后失效 `['generation','projects']` 查询；重试成功还会直接写入 `['generation','pipeline', id]` 缓存，避免等待一次往返。
- 展示给用户的错误文案由 `apiErrorMessage()` 从响应体 `detail` 或 `message` 中提取。

### 响应式状态

列表与详情页均覆盖加载中、未登录（`anonymous`）、空列表、失败重试与成功列表；详情页额外展示阶段日志、方案结构化字段、测试指标与版本链。

## 五、认证与账号

- 认证只使用平台账号体系：`client.auth.me()`、`client.auth.toLogin()`、`client.auth.logout()`，不新增第二套登录逻辑。
- `src/hooks/useAuthStatus.ts` 维护三态：`loading` / `authenticated` / `anonymous`。仅在 `me()` 返回空或抛错时判定未登录，业务接口失败不会触发跳转登录。
- `logout()` 先本地复位账号态再调用 SDK，避免顶栏残留登录态；平台登出接口异常时兜底回到首页，不让登出卡住。
- `src/contexts/AuthContext.tsx` 与 `useAuthStatus` 同源，避免出现两个事实来源。
- 登录后的落点由平台 `/auth/callback` 决定，应用无法指定回跳地址，因此「免费开始」意图用 `sessionStorage` 保存，并由 `StartFreeIntentWatcher` 在任意路由兜底消费：账号态为已登录且仍有未消费意图时回到首页并聚焦需求输入区。

## 六、视觉与工程约定

- 视觉以 `DESIGN.md` 为唯一规范：**暗色为唯一主题**，主色 `#C8F751` 占比不超过 10%，不使用蓝紫渐变。
- 语义化标签与充足对比度；键盘焦点环可见；支持 `prefers-reduced-motion`，系统减弱动效时停用背景动画。
- `index.html` 中的标题、描述与 logo 由概览系统通过 `data-mgx-overview` 标记管理，不手动修改。
- `src/pages/AuthCallback.tsx` 为平台只读文件，不做修改。
- 发布记录集中在 `src/data/changelog.ts`：新增版本时在数组**最前面**追加一条 `Release`，页面自动置顶并标记 `LATEST`，类型筛选计数与版本跳转同步更新；文档侧同步 `docs/changelog.md`。当前最新为 `v0.9.0`（测试用例与执行闭环）。
- 不在前端硬编码登录态相关的入口（如页脚「登录」），账号入口统一由 `SiteHeader` 的账号区表达。

## 七、构建配置要点

`vite.config.ts` 的关键行为：

- 开发服务器监听 `0.0.0.0`，端口取 `VITE_PORT`（默认 `3000`）；`/api` 代理到 `http://localhost:${BACKEND_PORT || 8000}`，`changeOrigin: true`。
- 文件监听使用 polling（`usePolling: true`，`interval: 600`），适配容器与远程工作区。
- 生产构建按 vendor 分包：`react-vendor`、`router-vendor`、`ui-vendor`、`form-vendor`、`utils-vendor`、`query-vendor`，`chunkSizeWarningLimit: 1000`。
- 站点地图由 `vite-plugin-sitemap` 生成（含 `robots.txt`），`lastmod` 取自 `prerender/blog-sitemap.js`。
- 仅当存在博客路由时（`getBlogRoutes()` 非空）才启用 `vite-prerender-plugin`，`renderTarget` 为 `#root`，预渲染脚本为 `prerender/blog.js`。

## 八、开发与验证

```bash
cd app/frontend
pnpm install
pnpm run dev      # 本地开发（Vite），预览服务会自动重载
pnpm run lint     # eslint --quiet ./src
pnpm run build    # 生产构建（含 / 与 /blog/ 预渲染），输出 dist/
pnpm run preview  # 预览构建产物
```

验收要求：`pnpm run lint && pnpm run build` 必须通过。新增依赖时保持 `package.json` 与源码导入同步，非相对导入必须已声明在 `package.json` 中。

## 九、后续阶段

阶段四（测试用例生成、执行与历史记录）已完成，测试面板已接入项目详情页，可自动或手动生成用例、执行并回溯历史结果。

- 阶段五：Bug 提交、记录与自动修复。
- 阶段六：对话式增量修改与版本回溯（前端需新增对话式编辑入口与版本对比视图）。
- 阶段七：自定义域名、团队协作与权限。

相关文档：`docs/mission.md`（产品纲领）、`docs/plan.md`（工程方案）、`docs/backend.md`（后端实现）、`docs/changelog.md`（平台发布记录）、`app/frontend/DESIGN.md`（视觉规范）。
