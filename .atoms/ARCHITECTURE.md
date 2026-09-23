# Architecture Design

## System Overview

纯前端单页应用，模拟 Atoms 这类 AI 应用生成平台的官网 + 产品演示页。核心链路：用户在首屏 Prompt Console 输入需求 → 前端按关键词匹配预设方案 → 定时推进六步生成时间线（解析需求 / 生成方案 / 编写代码 / 构建校验 / 测试验证 / 发布预览）→ 在预览窗渲染对应的真实迷你应用组件，完成后展示测试报告。次级页面（文档、登录、计费、模板详情）以统一占位页呈现。

## Tech Stack

Vite + React + TypeScript + Tailwind CSS + shadcn/ui + react-router-dom + lucide-react。无后端，所有内容来自本地静态数据。

## Module Design
| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| 路由壳 | 首页与次级占位路由挂载 | src/App.tsx |
| 首页 | Prompt Console、生成时间线、能力、模板库、定价、CTA | src/pages/Index.tsx |
| 顶栏 | 粘性导航与移动端菜单 | src/components/SiteHeader.tsx |
| 预览应用 | 三种迷你应用（看板/落地页/待办）真实 DOM 渲染 | src/components/MiniApp.tsx |
| 占位页 | 未建设模块的统一提示，模板详情复用 | src/pages/Placeholder.tsx |
| 静态数据 | 预设提示词、构建步骤、模板、能力、定价 | src/data/site.ts |
| 设计系统 | 颜色/字体/网格背景/动效 | src/index.css, DESIGN.md |

## Tech Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| 是否接入后端 | 否 | 本轮为演示页，生成流程用本地状态机即可表达产品逻辑 |
| 预览窗形态 | 真实组件渲染 | 比截图更可信，也便于后续接真实生成结果 |
| 模板缩略图 | CSS 线框 | 避免无意义 AI 配图，保持工程风一致性 |
| 生成动画 | setTimeout 状态机 | 首屏内容初始可见，不依赖滚动或观察器 |

## File Tree Plan

```
src/
  App.tsx
  index.css
  data/site.ts
  components/SiteHeader.tsx
  components/MiniApp.tsx
  pages/Index.tsx
  pages/Placeholder.tsx
DESIGN.md
```

## Implementation Guide

后续接入真实生成能力时：激活 Atoms Cloud 后端，将 `run()` 中的定时状态机替换为调用边缘函数的轮询；`PROMPT_PRESETS` 改为服务端返回的项目元数据；预览窗改为 iframe 加载真实部署地址。占位页可按路由逐个替换为真实页面，无需改动导航结构。
