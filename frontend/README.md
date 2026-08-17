# 识光简历 · 前端

Vue 3 单页应用：AI 对话挖掘经历 → 生成简历 → 质量评定 → 职位匹配与投递追踪。

## 启动方式

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://localhost:5173

需要后端一起跑（见根目录 `运行指南.md`，或直接用 `一键启动.bat`）。
如需改接口地址或切换 mock，复制 `.env.example` 为 `.env.local` 后修改。

## 技术栈

- Vue 3 + Vite
- Vue Router 4 + Pinia
- Naive UI（组件库）
- ECharts + vue-echarts（能力雷达图）
- Axios（默认 `VITE_USE_BACKEND=true`，调用真实后端；置否则走 `src/api/mock.js`）
- pdfjs-dist（上传简历时前端解析 PDF 文本）

## 页面

| 路由 | 说明 |
|------|------|
| `/` | 首页，输入岗位意向 |
| `/chat` | 多轮对话挖掘经历 |
| `/upload` | 上传已有简历做评定 |
| `/result` | 简历预览 / 质量报告 |
| `/dashboard` | 职位匹配、投递追踪、爬虫状态 |
| `/profile` | 个人中心，资料与数据概览 |
| `/admin/users` | 用户管理（管理员） |

## 部署

生产走 Cloudflare Pages（`npm run build` 输出 `dist/`），API 通过
Cloudflare Tunnel 暴露为 `api.sgjl.cloud`。前端**不能**用同源相对路径
调接口，原因见 `src/api/backend.js` 顶部注释。
