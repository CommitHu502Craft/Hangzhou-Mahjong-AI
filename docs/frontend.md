# Frontend Guide

## 概览

前端位于 `frontend/`，技术栈：
- Vue 3
- Vite
- TypeScript

目标：
- 提供面向市场化推广的可视化页面
- 强调项目卖点：规则可配置、训练可控、评测可信
- 支持移动端与桌面端

## 页面功能

1. 顶部导航与锚点跳转  
2. Hero 主视觉与 CTA  
3. 核心能力卡片展示  
4. 训练闭环流程卡片  
5. 指标看板  
6. FAQ 折叠交互  
7. 预约演示表单（校验 + 提交反馈状态）  
8. 与后端 `POST /api/leads` 联动提交  

## 本地运行

```powershell
uv run uvicorn api.server:app --host 127.0.0.1 --port 8000
cd frontend
npm install
npm run dev
```

说明：
- 前端默认请求 `/api/leads`。
- 开发环境通过 `frontend/vite.config.ts` 的 proxy 转发到 `http://127.0.0.1:8000`。
- 若需指定其他地址，可设置 `VITE_API_BASE_URL`。

## 生产构建

```powershell
cd frontend
npm run build
```

构建输出目录：`frontend/dist/`

## 主要文件

- `frontend/src/App.vue`：页面结构与交互逻辑
- `frontend/src/style.css`：视觉系统与响应式样式
- `frontend/index.html`：SEO 元信息与入口

## 视觉策略

- 字体：`Sora` + `Manrope`
- 主色：青绿色系（避免默认紫色风格）
- 辅色：暖橙强调
- 背景：多层径向渐变 + 半透明表面
- 动效：轻量入场动画与 hover 位移
