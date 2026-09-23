---
last_updated: 2026-09-22T07:20:00Z
status: active
---

# Project Context

## Project Overview

Atoms 风格 AI 应用生成平台的官网 + 产品演示页。用户用一句自然语言描述需求，页面展示「需求输入 → 六阶段生成流水线 → 可运行应用预览」的完整链路。当前交付 `docs/plan.md` 的**阶段一：纯前端演示版**，后端能力留待阶段二接入。

## Key Decisions
| Date | Decision | By | Rationale |
|------|----------|-----|-----------|
| 2026-09-22 | 阶段一不接入后端，生成流程用本地定时状态机表达 | Alex | 演示期只需表达产品逻辑，避免无需求的后端复杂度 |
| 2026-09-22 | 预览窗用真实 React 组件渲染，而非截图 | Alex | 与 mission 的「不生成点不动的假界面」一致，也更可信 |
| 2026-09-22 | 模板缩略图用 CSS 线框 | Alex | 避免无意义 AI 配图，保持工程风一致 |
| 2026-09-22 | 流水线由五步对齐为六步（补入测试验证） | Alex | 与 `docs/plan.md` 的状态模型及 mission 原则 2 对齐 |
| 2026-09-22 | 未落地模块统一使用「建设中」占位页，不伪造成已完成 | Alex | 落实 mission 原则 1 与原则 2 |

## Constraints

- 视觉规范以 `app/frontend/DESIGN.md` 为准：暗色为唯一主题、主色 `#C8F751` 占比 ≤10%、不使用蓝紫渐变。
- 产品边界以 `docs/mission.md` 为准：不做通用代码补全、不做拖拽搭建器、不做假界面。
- 前端固定为 shadcn/ui + Vite 技术栈；后端后续使用 Atoms Cloud，不自建第二套认证。
- 接入后端时，前端改动限定在 `run()`、`PROMPT_PRESETS` 与预览窗三处，不触碰导航与布局结构。
