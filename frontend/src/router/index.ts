import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '../utils/authStorage'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
    { path: '/register', name: 'register', component: () => import('../views/RegisterView.vue') },
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
      name: 'admin-dashboard',
      component: () => import('../views/admin/AdminDashboardView.vue'),
      meta: { requiresAdmin: true },
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAdmin && !getAccessToken('admin')) {
    return { path: '/admin/login' }
  }
  return true
})

export default router
