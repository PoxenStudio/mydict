import axios from 'axios'
import { setAccessToken, clearTokens, type AuthRole } from './authStorage'

/**
 * 用 refresh token 换新的 access token。
 *
 * refresh token 在服务端下发的 HttpOnly cookie 里（有效期 7 天，每次刷新滑动续期），
 * 前端读不到、也不需要读；请求体留空即可，兼容桌面端/扩展显式传 token 的老用法。
 */

const REFRESH_PATH: Record<AuthRole, string> = {
  user: '/api/auth/refresh',
  admin: '/api/admin/refresh',
}

// 刷新请求必须自带超时：路由守卫会 await 它，后端不可达时不能让导航一直挂着
const REFRESH_TIMEOUT_MS = 8000

// 并发请求同时 401 时只发一次刷新请求，其余等同一个 Promise
const inflight: Record<AuthRole, Promise<boolean> | null> = { user: null, admin: null }

export async function refreshSession(role: AuthRole): Promise<boolean> {
  if (inflight[role]) return inflight[role]

  const task = (async () => {
    try {
      const { data } = await axios.post<{ access_token: string }>(REFRESH_PATH[role], {}, {
        timeout: REFRESH_TIMEOUT_MS,
      })
      if (!data?.access_token) return false
      setAccessToken(role, data.access_token)
      return true
    } catch {
      // 刷新失败说明 cookie 也过期/失效了，清掉本地残留即可
      clearTokens(role)
      return false
    } finally {
      inflight[role] = null
    }
  })()

  inflight[role] = task
  return task
}
