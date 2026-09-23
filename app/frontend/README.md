# Atoms · AI 应用生成平台前端 Demo

本前端落地 `docs/mission.md` 与 `docs/plan.md` 的**阶段一：纯前端演示版**——访客在首屏用一句自然语言描述需求，即可看到「需求输入 → 六阶段生成流水线 → 可运行应用预览」的完整链路。无后端，所有内容来自本地静态数据。

## 页面与路由

| 路由 | 页面 | 状态 |
|------|------|------|
| `/` | 首页：需求输入台、生成时间线、预览窗、能力、模板库、定价、CTA | 已实现 |
| `/blog`、`/blog/:slug` | 博客索引与文章页，构建期预渲染 | 已实现 |
| `/auth/callback`、`/auth/error` | 认证回调与错误处理入口 | 已实现 |
| `/templates/:id` | 模板详情 | 建设中说明页 |
| `/docs` | 文档中心 | 建设中说明页 |
| `/changelog` | 更新日志：平台发布记录，按类型筛选与版本跳转 | 已实现 |
| `/signin` | 登录 | 建设中说明页 |
| `/billing` | 订阅与计费 | 建设中说明页 |

未落地的能力以统一的「建设中」说明页呈现，不伪造成已完成的功能。

## 关键文件

| 文件 | 职责 |
|------|------|
| `src/pages/Index.tsx` | 首页与生成演示：输入台、时间线推进、预览窗、模板库、定价、CTA |
| `src/components/MiniApp.tsx` | 三类迷你应用（增长看板 / 品牌落地页 / 团队待办）的真实 DOM 渲染 |
| `src/components/SiteHeader.tsx` | 粘性顶栏与移动端菜单 |
| `src/pages/Placeholder.tsx` | 未建设模块的统一说明页，模板详情复用 |
| `src/pages/Changelog.tsx` | 更新日志页：类型筛选、版本锚点跳转与发布记录时间线 |
| `src/data/site.ts` | 预设提示词、六阶段步骤与测试报告、模板、能力、定价 |
| `src/data/changelog.ts` | 平台发布记录数据源，按版本倒序，仅含呈现所需字段 |
| `src/lib/api.ts` | 预留的后端访问边界，阶段一未接入 |
| `src/index.css` | 设计令牌、网格背景、动效与 `prefers-reduced-motion` 处理 |
| `DESIGN.md` | 视觉规范来源，实现须服从该文档 |

## 生成演示链路

1. 用户输入需求（或点击示例提示胶囊），按 ⌘/Ctrl + Enter 或「生成应用」运行；空输入时主按钮禁用。
2. 前端按关键词匹配最接近的预设方案，并定时推进六个阶段：解析需求 → 生成方案 → 编写代码 → 构建校验 → 测试验证 → 发布预览。
3. 时间线以三态呈现：待执行（灰点）、进行中（青柠点脉冲）、已完成（成功色）。
4. 生成完成后预览窗渲染对应迷你应用，并展示测试报告（单元用例、冒烟用例、语句覆盖率）。

## 开发与验证

```bash
pnpm install
pnpm run dev      # 本地预览
pnpm run lint     # ESLint 检查
pnpm run build    # 生产构建，含 / 与 /blog/ 预渲染
```

接入真实生成能力时，改动集中在三处，不触碰导航与布局结构：`run()` 的定时状态机换成创建任务 + 轮询、`PROMPT_PRESETS` 换成服务端项目元数据、预览窗由 `MiniApp` 换成加载真实部署地址的 iframe。

## 工程约定

- 技术栈固定为 Vite + React + TypeScript + Tailwind CSS + shadcn/ui，UI 组件从 `@/components/ui` 引入，`@/` 别名指向 `src/`。
- 页面入口为 `src/main.tsx` 与 `src/App.tsx`，首页位于 `src/pages/Index.tsx`。
- 视觉以 `DESIGN.md` 为唯一规范：暗色为唯一主题，主色 `#C8F751` 占比不超过 10%，不使用蓝紫渐变。
- `index.html` 中的标题、描述与 logo 由概览系统通过 `data-mgx-overview` 标记管理，不手动修改。
