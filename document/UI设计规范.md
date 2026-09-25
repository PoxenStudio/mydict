# MyDict UI 设计规范

版本：v1.1
日期：2026-09-21
适用范围：前台查询/生词本页面 + 管理后台，共用同一套视觉系统

---

## 1. 设计原则

| 原则 | 说明 |
|---|---|
| **简洁统一** | 全站色彩、间距、圆角、字号只从本文档定义的 Token 取值，杜绝页面之间风格漂移；组件复用优先于"再画一个样式差不多的组件" |
| **有设计感** | 不做成千篇一律的后台表单站：用克制的品牌色、恰当的留白、精致的图标与卡片层次，让产品"看起来是被设计过的" |
| **立体** | 引入分层阴影（Elevation）体系，卡片、弹层、悬浮按钮有轻微"浮起"质感，避免纯扁平化导致的层级不清 |
| **清新** | 主色调选用清爽的青绿/蓝绿色系，贴合"词典/学习"场景的气质；大面积留白，避免高饱和度大色块堆砌 |
| **浅色/深色双主题** | 两套主题的语义色板独立定义、对比度均需达标，不是简单地给浅色主题做反色处理 |

## 2. 色彩系统

### 2.1 品牌色（Brand / Primary）

采用清新的青绿色作为品牌主色，取 10 级色阶（50 最浅 → 900 最深），用于强调按钮、链接、选中态、Logo：

| Token | 浅色主题取值（示例） | 用途 |
|---|---|---|
| `--color-brand-50` | `#EAFBF4` | 极浅背景（如选中行底色） |
| `--color-brand-100` | `#CFF5E4` | 浅底色/标签背景 |
| `--color-brand-300` | `#7FDDBA` | 次要强调 |
| `--color-brand-500` | `#2FBF8F` | **主品牌色**，主按钮/链接/高亮 |
| `--color-brand-600` | `#22A67B` | 主按钮 hover |
| `--color-brand-700` | `#178C66` | 主按钮 active/深色主题下的品牌色 |
| `--color-brand-900` | `#0B4A38` | 深色文字强调场景 |

> 以上色值为设计基线，实际视觉走查后可微调，但**必须整体替换色阶**而非单点改色，保持色阶过渡的一致性。

### 2.2 中性色（Neutral，背景/表面/边框/文字）

浅色、深色主题各自独立定义一套 9 级中性灰阶，而非用同一套灰阶加透明度简单反转：

| Token | 浅色主题 | 深色主题 | 用途 |
|---|---|---|---|
| `--color-bg-base` | `#F6F8F7`（微青灰底色，非纯白，呼应"清新"基调） | `#12161A` | 页面最底层背景 |
| `--color-bg-surface` | `#FFFFFF` | `#1B2126` | 卡片/面板表面 |
| `--color-bg-surface-raised` | `#FFFFFF`（配合阴影） | `#232B31`（比 surface 更亮一级，模拟灯光） | 弹层/下拉/浮起元素表面 |
| `--color-border` | `#E4E9E7` | `#2C363D` | 默认描边 |
| `--color-border-hover` | `#C7D1CD` | `#3C4850` | 交互态描边 |
| `--color-hover-tint` | `#EAFBF4`（即 `--color-brand-50`） | `color-mix(in srgb, 品牌色 500 18%, 当前表面色)` | 行/列表项/图标按钮的 hover 高亮底色；**不要**直接拿 `--color-brand-50` 做 hover 背景——那是固定浅色，配 `--color-text-primary` 这类深浅反转的文字在深色主题下会"亮底亮字"看不清 |
| `--color-text-primary` | `#1A2420` | `#EAF1EE` | 正文 |
| `--color-text-secondary` | `#5B6B65` | `#9DB0AA` | 次要文字 |
| `--color-text-tertiary` | `#8B9A94` | `#71827C` | 占位符/禁用文字 |

滚动条另有三个 Token，取值分别对齐 `--color-border-hover` 与 `--color-text-tertiary`，深浅两套主题都定义：

| Token | 浅色主题 | 深色主题 | 用途 |
|---|---|---|---|
| `--color-scrollbar-thumb` | `#C7D1CD` | `#3C4850` | 滚动条滑块 |
| `--color-scrollbar-thumb-hover` | `#8B9A94` | `#71827C` | 滑块 hover |
| `--color-scrollbar-track` | `transparent` | `transparent` | 轨道，透明以彻底融进底色 |

全屏遮罩（词条大图查看器）另有一组**不随主题切换**的 Token：看图时背景必须压到接近全黑，图片才看得清，浅色主题也不例外；浮在上面的按钮、提示条用半透明黑底 + 浅色字。

| Token | 取值（深浅主题相同） | 用途 |
|---|---|---|
| `--color-overlay-scrim` | `rgba(0, 0, 0, 0.86)` | 全屏遮罩底色 |
| `--color-overlay-control` | `rgba(0, 0, 0, 0.5)` | 遮罩上的按钮、提示条底色 |
| `--color-overlay-control-hover` | `rgba(0, 0, 0, 0.72)` | 遮罩上按钮 hover |
| `--color-overlay-text` | `#F2F5F4` | 遮罩上的文字与图标 |

滚动条一律通过 `.app-scrollbar` 工具类（`styles/scrollbar.css`）套用，不要在各组件里各写一份 `::-webkit-scrollbar`：它是全局伪元素，写在 scoped 样式里编译后带上属性选择器就永远匹配不上。

### 2.3 语义色（Semantic）

| Token | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--color-success` | `#2FBF8F`（复用品牌色） | `#3FD8A3` | 成功提示 |
| `--color-warning` | `#E8A33D` | `#F0B85C` | 警告（如限流临近） |
| `--color-danger` | `#E15656` | `#F1726F` | 危险/错误（如禁用、删除确认） |
| `--color-info` | `#4C8DFF` | `#6FA2FF` | 一般提示 |

### 2.4 对比度要求

- 正文文字（`--color-text-primary` / `--color-text-secondary`）与其所在背景的对比度 ≥ **4.5:1**（WCAG AA）。
- 大号标题文字/图标可放宽到 3:1。
- 深色主题不是浅色主题的简单反色：品牌色、语义色在深色底上需要**提高明度、降低饱和度**做单独适配（如上表 `--color-success` 深色取值比浅色更亮），否则在深色背景下发暗、观感变脏。

## 3. 立体感：阴影/层级（Elevation）体系

定义 5 级阴影，对应不同的"浮起"程度，浅色/深色分别取值（深色主题里纯黑投影几乎不可见，因此深色的层级感主要靠**表面亮度分级 + 微弱高光边框**实现，阴影仅作为轻微补充）：

| Token | 浅色主题 | 深色主题 | 典型场景 |
|---|---|---|---|
| `--shadow-elevation-0` | 无阴影，仅 `--color-border` 描边 | 同左 | 普通卡片（列表内的行） |
| `--shadow-elevation-1` | `0 1px 2px rgba(16,24,21,0.06)` | `0 1px 2px rgba(0,0,0,0.4)` + 顶部 1px `rgba(255,255,255,0.04)` 内高光 | 查询结果卡片、静态面板 |
| `--shadow-elevation-2` | `0 4px 12px rgba(16,24,21,0.08)` | 同规则，透明度加深 + 表面色升一级 | Hover 态卡片、下拉菜单 |
| `--shadow-elevation-3` | `0 8px 24px rgba(16,24,21,0.10)` | 同上 | 弹层 Modal、Popover |
| `--shadow-elevation-4` | `0 16px 40px rgba(16,24,21,0.14)` | 同上 | 全局通知/Toast、最高层浮层 |

使用规则：**同一时刻页面上出现的阴影层级差要 ≥ 1 级**，才能形成清晰的前后关系（例如 Modal 用 elevation-3，Modal 内的下拉用 elevation-2 会显得穿模，应至少用 elevation-3 或更高）。

## 4. 圆角（Radius）

| Token | 取值 | 用途 |
|---|---|---|
| `--radius-sm` | 4px | 标签/徽标、输入框内的小控件 |
| `--radius-md` | 8px | 按钮、输入框 |
| `--radius-lg` | 12px | 卡片、面板 |
| `--radius-xl` | 16px | 大型容器、Modal |
| `--radius-full` | 999px | 头像、圆形按钮、Pill 标签（如 ECDICT 的"四级""牛津3000"徽标） |

## 5. 间距（Spacing）

采用 8px 基准网格，特殊场景允许 4px 半步：

`--space-1: 4px` `--space-2: 8px` `--space-3: 12px` `--space-4: 16px` `--space-5: 24px` `--space-6: 32px` `--space-7: 48px` `--space-8: 64px`

组件内边距、元素间距一律取上述 Token，禁止出现如 `13px`、`19px` 这类随意数值。

### 5.1 尺寸（Size）

页面容器、弹窗、浮层、滚动区与控件高度取下列 Token，不在组件里写死像素：

| Token | 取值 | 用途 |
| --- | --- | --- |
| `--size-content-md` | 960px | 管理后台列表页内容区最大宽度 |
| `--size-content-lg` | 1220px | 列多的宽列表页（词典管理：勾选/拖拽/名称/格式/语言/词条数/状态/操作共 8 列） |
| `--size-dialog-sm` | 420px | 表单较短的弹窗宽度 |
| `--size-dialog-md` | 560px | 表单较长/含列表的弹窗宽度 |
| `--size-popover-md` | 360px | 悬浮提示（文件清单等）宽度 |
| `--size-popover-lg` | 460px | 悬浮提示（长路径清单）宽度 |
| `--size-scroll-sm` | 320px | 弹窗内可滚动列表的最大高度 |
| `--size-scroll-md` | 360px | 弹窗内可滚动结果区的最大高度 |
| `--size-control-md` | 32px | 与 Element Plus 默认控件同高的行/图标列宽度 |
| `--size-control-lg` | 44px | 悬浮按钮（回到顶部/回到底部）的圆形直径，单指可稳妥点中 |
| `--size-scrollbar-width` | 8px | 细滚动条宽度 |

## 6. 字体与排版

- 字体栈：`-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif`（不引入自定义 Web Font，减小体积、避免中文字重下载开销）。
- 等宽字体栈（路径、代码等）：`--font-family-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`。
- 音标/英文释义可选衬线备用栈以做区分：`"Noto Serif SC", Georgia, serif`（可选，非强制）。
- 字号阶梯：`--text-xs:12px` `--text-sm:13px` `--text-base:14px` `--text-md:16px` `--text-lg:18px` `--text-xl:20px` `--text-2xl:24px` `--text-3xl:32px`
- 字重：正文 400，强调/小标题 500，标题 600，重要数字（如统计大盘的 KPI 数字）可用 700。
- 行高：正文 1.6，标题 1.3，单行控件（按钮/输入框）1.0（由 padding 控制视觉高度）。

## 7. 核心组件风格指南

### 7.1 查询首页搜索框
- 页面视觉焦点，采用较大尺寸（高度 ≥ 48px）、`--radius-full` 或 `--radius-lg` 圆角、`--shadow-elevation-1` 静态阴影，获得焦点时阴影升到 `--shadow-elevation-2` 并显示品牌色描边，体现"清新有质感"的首屏印象。
- 页面为单列居中布局（最大宽度 `--size-content-md`）：自上而下依次是站名标语、搜索框、检索范围、结果列表；搜索提示语与部署版本号收在页面底部的页脚（`.site-footer`）。
- 检索范围只对登录用户显示（列出其可用词典），访客（开放使用）没有这一行。默认收起，搜索框下方居中显示一行摘要（「检索范围：全部词典（N）」或「已选 x / N 部」）与右箭头；点击后箭头转向下方，在摘要下方展开与搜索框同宽的面板（筛选框、语言快捷按钮、词典列表）。词典项以「[语言]词典名」的紧凑形式显示（语言部分用次要文字色，整项超长时一起省略），列表按 240px 最小列宽自动排成多列，超过 `--size-scroll-md` 时在列表内滚动；复选框用 `accent-color: --color-brand-500`。

### 7.2 词典释义卡片
- 每部词典的释义作为一张独立卡片（`--shadow-elevation-1` + `--radius-lg`），卡片头部展示词典名称小标签，卡片内单词加粗、音标次要色、释义正文分词性分段；ECDICT 的标签（tag/collins/oxford/exchange）用 `--radius-full` 的 Pill 徽标，配合语义色区分（如考纲标签用 `--color-info` 浅底、词频/星级用 `--color-brand` 浅底）。
- 多词典结果并列展示时，卡片间距取 `--space-2`；卡片头部（`.panel-header`）的垂直内边距取 `--space-1`，让折叠状态的标题行尽量矮——一次查询常命中十几部词典，标题行太高会把后续词典挤出屏幕。

### 7.3 按钮
- 主按钮：`--color-brand-500` 填充，hover `--color-brand-600`，active `--color-brand-700`，`--radius-md`。
- 次按钮：透明底 + `--color-border` 描边，hover 时背景转 `--color-hover-tint`（浅色主题即 `--color-brand-50`，深色主题是掺了品牌色的暗底，见 2.2）。
- 危险操作（禁用 Token、删除词典）统一用 `--color-danger` 的次按钮样式，且必须二次确认弹窗。

### 7.4 生词本 / 收藏按钮
- 未收藏：描边星标图标 + 次按钮样式；已收藏：`--color-brand-500` 实心星标 + 轻微缩放动效（100ms），给用户明确的即时反馈。

### 7.5 管理后台数据表格
- 表头使用 `--color-bg-base` 略深于表体的底色做区分，行 hover 用 `--color-hover-tint` 高亮，操作列按钮统一左对齐（按钮较多换行时保持每行都从左边起排，不因换行产生参差不齐的右对齐观感）、用文字按钮（非图标堆砌）保持"简洁统一"。

### 7.6 空状态 / 加载态 / 错误态
- 空状态：居中图形（线性风格图标，非写实插画）+ 一句引导文案 + 可选操作按钮（如生词本为空时引导去查询页）。
- 加载态：骨架屏（Skeleton）优先于 Loading 转圈，查询结果、统计图表、列表页统一使用骨架屏，减少"卡顿感"。
- 错误态：区分"网络错误可重试"与"无结果"两种情况，前者给重试按钮，后者给友好文案（如"暂未收录该词，欢迎补充词典"）。

### 7.7 悬浮滚动按钮（回到顶部 / 回到底部）
- 形态：右下角竖排两个圆形按钮（直径 `--size-control-lg`、`--radius-full`），间距 `--space-2`，回到顶部在上、回到底部在下；图标是 `fill: currentColor` 的内联 SVG，随主题自动变色，不需要准备两套图标。
- 底色：`color-mix(in srgb, var(--color-bg-surface-raised) 92%, transparent)` + `backdrop-filter: blur(6px)`，浮在词条正文上时不把内容整块切掉；hover 转为实底 `--color-bg-surface-raised`、阴影升到 `--shadow-elevation-2`，并轻微放大。
- 显隐：滚动超过 200px 才整体出现（淡入淡出）；距底部不足 200px 时单独隐藏"回到底部"，只留"回到顶部"。
- 层级：`z-index: 5`——高于页面内容，但低于移动端抽屉与 Element Plus 浮层，抽屉打开时自然被盖住。
- 动效：300ms easeOutCubic 自行补间（不用 `behavior: 'smooth'`，便于统一降级）；系统开启"减少动态效果"时改为直接跳转。
- 移动端（< 640px）缩到 38px 并更贴边。

### 7.8 iframe 释义的暗色适配
- 词典原文自带写死的颜色（白底黑字最常见），暗色主题下必须翻掉，否则是一整块刺眼的白。
- 覆盖原则是**只翻明确写着黑/白的呈现**（`<font color="#000">`、内联 `style` 里的 `color:#000` / `background:#fff`），词典自带的红字、彩色表格等语义色一律保留。禁止用 `* { color: … !important }` 这类通配覆盖——那等于把词典排版一起改掉。
- 实现上由后端在渲染词条时注入（见《技术方案设计.md》"词条渲染"），不改数据库里的释义，所以**新导入的词典自动适用**。

## 8. 主题切换

- 支持三种模式：**浅色 / 深色 / 跟随系统**，入口放在导航栏右上角（图标按钮，太阳/月亮/自动图标切换）。
- 默认取值：未登录/首次访问时跟随系统 `prefers-color-scheme`；用户手动切换后记忆该选择（本地存储），下次访问优先使用用户选择而非系统设置。
- 切换动画：主题切换时对 `background-color`/`color` 等关键属性加 150ms 过渡，避免生硬跳变（但不对布局属性做过渡，防止切换时页面"抖动"）。

## 9. 响应式断点

| 断点 | 范围 | 说明 |
|---|---|---|
| `--bp-mobile` | < 640px | 单栏布局，管理后台侧边栏收起为抽屉 |
| `--bp-tablet` | 640–1024px | 双栏/精简侧边栏 |
| `--bp-desktop` | ≥ 1024px | 完整布局（后台侧边栏常驻、查询页可并列展示多词典结果） |

## 10. 可访问性（Accessibility）

- 所有可交互元素需有可见的 `:focus-visible` 态（品牌色描边，不可仅靠 hover 色区分）。
- 图标按钮需配 `aria-label`；表单输入需关联 `<label>`。
- 色彩不作为传递信息的唯一方式（如"限流告警"除变红外还需搭配文字/图标）。

---

技术实现层面（Token 如何在代码中落地为 CSS 变量、深浅主题如何切换、如何与 Element Plus 主题联动）见《技术方案设计.md》"结构化样式定义"一节。
