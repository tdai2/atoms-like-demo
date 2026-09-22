export type MiniAppKind = 'dashboard' | 'landing' | 'todo';

export interface PromptPreset {
  id: string;
  label: string;
  prompt: string;
  kind: MiniAppKind;
  appName: string;
  stack: string[];
}

export const PROMPT_PRESETS: PromptPreset[] = [
  {
    id: 'dashboard',
    label: '增长数据看板',
    prompt: '做一个 SaaS 增长数据看板，包含核心指标卡、趋势图和渠道排行',
    kind: 'dashboard',
    appName: 'growth-dashboard',
    stack: ['React', 'Recharts', 'Tailwind'],
  },
  {
    id: 'landing',
    label: '产品落地页',
    prompt: '做一个咖啡订阅品牌的落地页，要有首屏主视觉、套餐价格和订阅表单',
    kind: 'landing',
    appName: 'brew-club-landing',
    stack: ['React', 'Tailwind', 'Vite'],
  },
  {
    id: 'todo',
    label: '团队待办应用',
    prompt: '做一个团队任务协作应用，支持添加任务、勾选完成和按状态统计',
    kind: 'todo',
    appName: 'team-tasks',
    stack: ['React', 'Zustand', 'Tailwind'],
  },
];

export interface BuildStep {
  id: string;
  title: string;
  detail: string;
}

export const BUILD_STEPS: BuildStep[] = [
  { id: 'parse', title: '解析需求', detail: '拆解意图、实体与页面结构' },
  { id: 'plan', title: '生成方案', detail: '选择技术栈与组件层级' },
  { id: 'code', title: '编写代码', detail: '生成 React 组件与样式' },
  { id: 'build', title: '构建校验', detail: '类型检查与依赖安装' },
  { id: 'deploy', title: '发布预览', detail: '部署到临时预览域名' },
];

export interface TemplateItem {
  id: string;
  name: string;
  summary: string;
  category: '数据' | '营销' | '工具' | '电商';
  accent: string;
  wire: 'chart' | 'hero' | 'list' | 'grid';
}

export const TEMPLATES: TemplateItem[] = [
  { id: 'kpi', name: '指标监控台', summary: '实时 KPI、告警阈值与趋势对比', category: '数据', accent: '#c8f751', wire: 'chart' },
  { id: 'crm', name: '轻量 CRM', summary: '客户管线、跟进记录与转化漏斗', category: '工具', accent: '#7dd3fc', wire: 'list' },
  { id: 'launch', name: '新品发布页', summary: '首屏主视觉、特性列表与预约表单', category: '营销', accent: '#f0abfc', wire: 'hero' },
  { id: 'shop', name: '单品商店', summary: '商品详情、购物车与结算流程', category: '电商', accent: '#fbbf24', wire: 'grid' },
  { id: 'docs', name: '文档站点', summary: '侧边导航、搜索与代码高亮', category: '工具', accent: '#4ade80', wire: 'list' },
  { id: 'wait', name: '等待列表页', summary: '邮箱收集、邀请码与社交证明', category: '营销', accent: '#c8f751', wire: 'hero' },
];

export const TEMPLATE_CATEGORIES = ['全部', '数据', '营销', '工具', '电商'] as const;

export interface Capability {
  id: string;
  title: string;
  body: string;
  tag: string;
}

export const CAPABILITIES: Capability[] = [
  { id: 'agent', title: '多智能体协作', body: '产品、架构、工程与测试角色分工推进，每一步产出可追溯。', tag: 'agents' },
  { id: 'fullstack', title: '全栈一次生成', body: '前端界面、数据表与接口同时生成，开箱即是可运行应用。', tag: 'fullstack' },
  { id: 'iterate', title: '对话式迭代', body: '用自然语言继续追加需求，增量修改而非重写整个项目。', tag: 'iterate' },
  { id: 'deploy', title: '一键发布', body: '内置构建与托管，生成即得可分享的预览链接与自定义域名。', tag: 'deploy' },
];

export interface PlanItem {
  id: string;
  name: string;
  price: string;
  unit: string;
  desc: string;
  features: string[];
  highlight?: boolean;
}

export const PLANS: PlanItem[] = [
  {
    id: 'free',
    name: 'Starter',
    price: '¥0',
    unit: '/ 月',
    desc: '体验完整生成流程',
    features: ['每月 20 次生成', '公开预览链接', '社区模板库'],
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '¥199',
    unit: '/ 月',
    desc: '面向独立开发者与小团队',
    features: ['每月 1000 次生成', '私有项目与自定义域名', '数据库与接口生成', '优先构建队列'],
    highlight: true,
  },
  {
    id: 'team',
    name: 'Team',
    price: '定制',
    unit: '',
    desc: '面向需要协作与合规的团队',
    features: ['成员与权限管理', '私有部署通道', '审计日志', '专属支持'],
  },
];
