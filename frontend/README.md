# Job Copilot · 前端

AI 求职副驾驶比赛 Demo 的前端项目。

## 启动方式

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://localhost:5173

## 技术栈

- Vue 3 + Vite
- Vue Router 4 + Pinia
- Naive UI（组件库）
- ECharts + vue-echarts（雷达图）
- Axios（保留，当前用 mock 数据）

## 演示流程

1. 首页：输入岗位意向（如"我想做产品经理"）
2. 对话页：与 AI 进行多轮经历挖掘对话
3. 过渡页：粒子加载动画（2-3 秒）
4. 结果页：Tab 切换查看简历预览 / 质量报告
