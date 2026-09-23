export type ChangeType = 'feature' | 'improve' | 'fix';

export interface ChangeItem {
  type: ChangeType;
  text: string;
}

export interface Release {
  /** 用于锚点跳转，例如 /changelog#v0.6.0 */
  version: string;
  /** ISO 日期，直接用于展示与 <time dateTime> */
  date: string;
  title: string;
  summary: string;
  tags: string[];
  items: ChangeItem[];
}

/** 平台自身的发布记录，按版本倒序排列。 */
export const CHANGELOG: Release[] = [
  {
    version: 'v0.6.0',
    date: '2026-09-22',
    title: '生成流水线对齐六阶段',
    summary: '把「测试验证」补进主流程，生成过程由五步变为六步，每一步的产出都可追溯。',
    tags: ['pipeline', 'testing'],
    items: [
      { type: 'feature', text: '新增「测试验证」阶段：单元用例、冒烟用例与语句覆盖率随应用一起产出。' },
      { type: 'feature', text: '生成完成后展示测试报告面板，失败用例会被回灌到代码生成阶段重试一次。' },
      { type: 'improve', text: '时间线支持 pending / running / done 三态与脉冲动画，长任务等待过程不再空白。' },
      { type: 'improve', text: '尚未落地的次级页面统一为「建设中」说明页，不再出现点不动的假界面。' },
      { type: 'fix', text: '修复生成过程中刷新页面后时间线停在 running 状态的问题。' },
    ],
  },
  {
    version: 'v0.5.0',
    date: '2026-09-12',
    title: '模板库与分类筛选',
    summary: '模板从零散示例整理为可筛选的画廊，选好起点后可直接带参生成。',
    tags: ['templates', 'ui'],
    items: [
      { type: 'feature', text: '新增模板画廊，覆盖数据、营销、工具、电商四个分类。' },
      { type: 'feature', text: '新增模板详情入口，可查看适用场景与推荐技术栈。' },
      { type: 'improve', text: '筛选无结果时给出等宽提示与一键重置，不再显示空白区域。' },
      { type: 'fix', text: '修复切换分类后滚动位置丢失、页面跳动的问题。' },
    ],
  },
  {
    version: 'v0.4.0',
    date: '2026-08-28',
    title: '暗色工程风设计系统',
    summary: '统一颜色、字体与间距令牌，后续页面不再各自定义视觉。',
    tags: ['design-system', 'a11y'],
    items: [
      { type: 'feature', text: '新增设计令牌：背景、表面、边框、主色与状态色，暗色为唯一主题。' },
      { type: 'feature', text: '新增原子网格背景与低速粒子动效，降低首屏空洞感。' },
      { type: 'improve', text: '标题与代码标记改用 Space Grotesk 与 JetBrains Mono，弱文字与背景对比度提升。' },
      { type: 'improve', text: '支持 prefers-reduced-motion，系统设置减弱动效时停用背景动画。' },
      { type: 'fix', text: '修复键盘 Tab 到输入框与按钮时焦点环不可见的问题。' },
    ],
  },
  {
    version: 'v0.3.0',
    date: '2026-08-14',
    title: '多智能体协作编排',
    summary: '产品、架构、工程与测试角色分工推进，需求到产物之间不再是一个黑盒。',
    tags: ['agents', 'orchestration'],
    items: [
      { type: 'feature', text: '新增角色分工编排：需求解析、方案设计、代码实现与测试校验由不同角色接力完成。' },
      { type: 'feature', text: '每个阶段的产出单独落库，可回看方案的选型理由与实现范围。' },
      { type: 'improve', text: '提示词模板按角色注入，减少长需求在传递过程中的信息丢失。' },
      { type: 'fix', text: '修复超长需求被静默截断、生成结果与描述不符的问题。' },
    ],
  },
  {
    version: 'v0.2.0',
    date: '2026-07-30',
    title: '全栈一次生成',
    summary: '前端界面、数据表与接口在同一次生成中产出，拿到即可运行。',
    tags: ['fullstack', 'storage'],
    items: [
      { type: 'feature', text: '新增数据表与接口生成，支持登录态与按用户隔离的数据读写。' },
      { type: 'feature', text: '新增对象存储托管生成产物，图纸文件不再进入业务库。' },
      { type: 'improve', text: '复用依赖缓存，二次生成的构建耗时平均下降约四成。' },
      { type: 'fix', text: '修复依赖安装超时导致构建阶段整体失败的问题。' },
    ],
  },
  {
    version: 'v0.1.0',
    date: '2026-07-16',
    title: '首个可用版本',
    summary: '一句话描述需求，得到可访问的应用预览链接。',
    tags: ['core'],
    items: [
      { type: 'feature', text: '支持用一句自然语言需求生成可运行的 Web 应用。' },
      { type: 'feature', text: '生成结束后输出可分享的预览链接。' },
      { type: 'improve', text: '输入台默认聚焦，支持 ⌘/Ctrl + Enter 直接运行。' },
      { type: 'fix', text: '修复空输入时仍可提交、产生无意义任务的问题。' },
    ],
  },
];
