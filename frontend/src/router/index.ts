import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '../utils/authStorage'
import { refreshSession } from '../utils/session'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
    { path: '/register', name: 'register', component: () => import('../views/RegisterView.vue') },
    {
      path: '/vocab',
      name: 'vocab',
      component: () => import('../views/VocabView.vue'),
      meta: { requiresUser: true },
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('../views/HistoryView.vue'),
      meta: { requiresUser: true },
    },
    {
      path: '/admin/setup',
      name: 'admin-setup',
      component: () => import('../views/admin/AdminSetupView.vue'),
    },
    {
      path: '/admin/login',
      name: 'admin-login',
      component: () => import('../views/admin/AdminLoginView.vue'),
    },
    {
      path: '/admin',
      component: () => import('../views/admin/AdminLayout.vue'),
      meta: { requiresAdmin: true },
      children: [
        {
          path: '',
          name: 'admin-dashboard',
          component: () => import('../views/admin/AdminDashboardView.vue'),
        },
        {
          path: 'dictionaries',
          name: 'admin-dictionaries',
          component: () => import('../views/admin/DictionaryManagementView.vue'),
        },
        {
          path: 'tokens',
          name: 'admin-tokens',
          component: () => import('../views/admin/AdminTokensView.vue'),
        },
        {
          path: 'users',
          name: 'admin-users',
          component: () => import('../views/admin/AdminUsersView.vue'),
        },
        {
          path: 'stats',
          name: 'admin-stats',
          component: () => import('../views/admin/AdminStatsView.vue'),
        },
        {
          path: 'settings',
          name: 'admin-settings',
          component: () => import('../views/admin/AdminSettingsView.vue'),
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  // 本地没有 access token 不代表没登录：HttpOnly cookie 里的 refresh token 可能还有效
  // （7 天滑动），先静默换一张再决定要不要跳登录页。
  if (to.meta.requiresAdmin && !getAccessToken('admin')) {
    if (!(await refreshSession('admin'))) return { path: '/admin/login' }
  }
  if (to.meta.requiresUser && !getAccessToken('user')) {
    if (!(await refreshSession('user'))) return { path: '/login' }
  }
  return true
})

export default router
