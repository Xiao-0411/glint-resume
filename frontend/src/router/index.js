import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { transition: 'fade' }
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { transition: 'slide' }
  },
  {
    path: '/upload',
    name: 'upload',
    component: () => import('@/views/UploadView.vue'),
    meta: { transition: 'fade' }
  },
  {
    path: '/result',
    name: 'result',
    component: () => import('@/views/ResultView.vue'),
    meta: { transition: 'fade' }
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { transition: 'fade' }
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { transition: 'fade' }
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/AdminUsersView.vue'),
    meta: { transition: 'fade' }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
