# MyDict 项目规则

产品/技术文档分两处：`doc/`（内部使用，产品需求文档、实施计划，不对外公开、git 已忽略）与 `document/`（技术方案、UI 设计规范、代码规范 + 素材如 logo，随代码一起提交）。改动代码前先确认是否涉及以下规范，不确定就去读对应文档，不要凭空假设。

## UI 相关改动 → 必须遵守 `document/UI设计规范.md`

- 设计原则：简洁统一、立体（分层阴影 Elevation）、清新（青绿主色调、大留白）、浅色/深色双主题。
- 所有颜色/间距/圆角/阴影/字号一律用 Design Token（CSS 变量），**禁止硬编码数值**（如 `#2FBF8F`、`12px`），一次性特殊值需注释说明原因。
- Token 的技术实现（文件组织、命名规范、深浅主题切换机制、与 Element Plus 联动）见 `document/技术方案设计.md` 第 7 节「前端样式架构」。
- 新增视觉规则先更新 `document/UI设计规范.md` 与技术方案第 7 节的 Token 表，再落到 `frontend/src/styles/tokens/`，不要出现文档里没记录的"野生 Token"。

## 代码相关改动 → 必须遵守 `document/代码规范.md`

- 前端：Vue3 `<script setup lang="ts">`（不混用 Options API），Pinia 按领域拆 store，接口调用集中在 `src/api/`（组件内不直接 `import axios`），组件样式默认 `scoped` 且只消费 `var(--token)`。
- 后端：FastAPI 路由层只做参数校验/鉴权/调用 service，业务逻辑下沉 `services/`；所有表结构变更必须走 Alembic migration，不手改数据库；`models`（ORM）与 `schemas`（Pydantic）严格分离。
- Git：Conventional Commits（`feat`/`fix`/`docs`/`style`/`refactor`/`perf`/`test`/`chore`）。
- 接口一旦新增/修改，必须同步更新 `document/技术方案设计.md` 第 4 节接口表，代码与文档不允许脱节。
- **注释**：不写冗长注释，除复杂逻辑外尽量不加注释；注释里不要引用 `doc/`、`document/` 下的文档路径。

## 何时读哪份文档

| 场景 | 读这份 |
|---|---|
| 任何前端样式/组件视觉改动 | `document/UI设计规范.md` + `document/技术方案设计.md` 第 7 节 |
| 目录结构/命名/Lint/测试/Git 约定 | `document/代码规范.md` |
| 数据模型/API 设计/部署/词典解析原理 | `document/技术方案设计.md` |
| 功能范围边界、某个设计为什么这么定 | `doc/产品需求文档.md` 第 10 节「决策记录」 |
| 不确定下一步该做什么 | `doc/实施计划.md`（按 Step 0-7 的任务清单与验收标准推进） |
