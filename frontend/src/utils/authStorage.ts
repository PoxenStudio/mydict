import { ref } from 'vue'

// 管理员/用户 Token 分别存储在不同 key 下，互不影响；request.ts 与各 auth store 共用同一套读写逻辑，避免循环依赖。
// 注意：refresh token 不放这里——它由服务端写在 HttpOnly cookie 里（见 utils/session.ts）。
const KEYS = {
  admin: { access: 'mydict-admin-access' },
  user: { access: 'mydict-user-access' },
} as const

// 旧版本把 refresh token 也存在 localStorage，升级后残留的键一并清掉
const LEGACY_REFRESH_KEYS = ['mydict-admin-refresh', 'mydict-user-refresh']

export type AuthRole = keyof typeof KEYS

// localStorage 本身不是 Vue 响应式来源，直接在 Pinia getter 里读它不会在登录/登出时
// 触发视图更新（要等下次整页刷新）；改成这份 ref 做唯一真源，setAccessToken/clearTokens
// 统一更新它——不管是 store 的 login/logout 调用的，还是 request.ts 拦截器在 401
// 时直接调用的，订阅方都能立刻拿到最新状态。
const loggedInRefs: Record<AuthRole, ReturnType<typeof ref<boolean>>> = {
  admin: ref(Boolean(localStorage.getItem(KEYS.admin.access))),
  user: ref(Boolean(localStorage.getItem(KEYS.user.access))),
}

export function isLoggedInRef(role: AuthRole) {
  return loggedInRefs[role]
}

export function getAccessToken(role: AuthRole): string | null {
  return localStorage.getItem(KEYS[role].access)
}

export function setAccessToken(role: AuthRole, accessToken: string): void {
  localStorage.setItem(KEYS[role].access, accessToken)
  loggedInRefs[role].value = true
}

export function clearTokens(role: AuthRole): void {
  localStorage.removeItem(KEYS[role].access)
  for (const key of LEGACY_REFRESH_KEYS) localStorage.removeItem(key)
  loggedInRefs[role].value = false
}
