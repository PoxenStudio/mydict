import axios, { type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { clearTokens, getAccessToken } from '../utils/authStorage'

const request = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

request.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const isAdminApi = config.url?.startsWith('/admin')
  const token = getAccessToken(isAdminApi ? 'admin' : 'user')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    const code = error.response?.data?.code
    const isAdminApi = (error.config?.url as string | undefined)?.startsWith('/admin')
    const message = error.response?.data?.message

    // code === 'invalid_credentials' 是登录/改密时用户名密码错误，属于正常业务错误，
    // 不代表登录态失效，只应提示不应清 token/跳转（否则会把当前登录页面的失败尝试
    // 误判成会话过期，静默跳回同一个登录页，界面上看起来像“点了没反应”）
    if (status === 401 && code === 'unauthorized') {
      clearTokens(isAdminApi ? 'admin' : 'user')
      router.push(isAdminApi ? '/admin/login' : '/login')
    } else if (status === 403) {
      ElMessage.warning(message ?? '无权限执行该操作')
    } else if (status === 429) {
      ElMessage.warning('操作过于频繁，请稍后再试')
    } else if (message) {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  },
)

export default request
