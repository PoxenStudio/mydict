# frontend

MyDict 的 Vue3 SPA（前台查询/生词本 + 管理后台），构建产物由根目录 Dockerfile 打包进后端镜像统一托管。

```bash
npm install
npm run dev      # 本地开发，默认代理后端 /api（见 vite.config.ts）
npm run build    # 类型检查 + 生产构建
npm run lint
npm run format
```

目录结构、样式 Token 约定见根目录 `document/代码规范.md`、`document/UI设计规范.md`。
