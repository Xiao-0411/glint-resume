import { createRouter, createWebHistory } from 'vue-router'

const SITE_NAME = '识光简历 Glint'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { transition: 'fade', title: 'AI 智能简历生成与优化平台 | 10 分钟做出让 HR 眼前一亮的简历' }
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { transition: 'slide', title: 'AI 对话生成简历' }
  },
  {
    path: '/upload',
    name: 'upload',
    component: () => import('@/views/UploadView.vue'),
    meta: { transition: 'fade', title: '上传简历 AI 优化诊断' }
  },
  {
    path: '/result',
    name: 'result',
    component: () => import('@/views/ResultView.vue'),
    meta: { transition: 'fade', title: '简历结果' }
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { transition: 'fade', title: '求职看板' }
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { transition: 'fade', title: '个人中心' }
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/AdminUsersView.vue'),
    meta: { transition: 'fade', title: '用户管理' }
  },
  // 未知路径回到首页（旧的 #/xxx hash 链接由 main.js 启动时改写为 history 路径）
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

// history 模式：每个页面有独立 URL（/chat、/upload），搜索引擎才能分别收录
// Cloudflare Pages 的 public/_redirects 已配置 SPA 回退
const router = createRouter({
  history: createWebHistory(),
  routes
})

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `${title} - ${SITE_NAME}` : SITE_NAME
})

export default router
