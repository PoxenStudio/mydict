import axios, { type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { clearTokens, getAccessToken } from '../utils/authStorage'
import { refreshSession } from '../utils/session'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** 后台请求（预取等）：失败时不弹提示、不跳登录页，由真正发起的那次请求处理 */
    silent?: boolean
    /** 已经用刷新后的 access token 重试过一次，避免 401 → 刷新 → 401 的死循环 */
    _retried?: boolean
  }
}

let maintenanceHandler: (() => void) | undefined

// 服务启动流程未就绪时业务接口统一返回 503 maintenance，由系统状态 store 接手展示维护页
export function onMaintenance(handler: () => void) {
  maintenanceHandler = handler
}

const request = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

function isAuthEndpoint(url: string | undefined): boolean {
  // 用户端是 /auth/*，管理端是 /admin/*（不是 /admin/auth/*）
  return Boolean(url && /^(?:\/auth|\/admin)\/(?:login|refresh|setup)$/.test(url))
}

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
  async (error) => {
    const status = error.response?.status
    const code = error.response?.data?.code
    const url = error.config?.url as string | undefined
    const isAdminApi = url?.startsWith('/admin')
    const role = isAdminApi ? 'admin' : 'user'
    const message = error.response?.data?.message

    // access token 只有 2 小时：过期不等于登录失效。先用 HttpOnly cookie 里的
    // refresh token 静默换一张（有效期 7 天、滑动续期），成功就重放原请求。
    if (status === 401 && code === 'unauthorized' && !isAuthEndpoint(url) && !error.config?._retried) {
      error.config._retried = true
      if (await refreshSession(role)) {
        return request(error.config)
      }
    }

    // code === 'invalid_credentials' 是登录/改密时用户名密码错误，属于正常业务错误，
    // 不代表登录态失效，只应提示不应清 token/跳转（否则会把当前登录页面的失败尝试
    // 误判成会话过期，静默跳回同一个登录页，界面上看起来像“点了没反应”）
    if (status === 503 && code === 'maintenance') {
      maintenanceHandler?.()
    } else if (error.config?.silent) {
      // 静默请求不打扰用户
    } else if (status === 401 && code === 'unauthorized') {
      clearTokens(role)
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
