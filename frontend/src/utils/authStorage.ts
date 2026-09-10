import { ref } from 'vue'

// 管理员/用户 Token 分别存储在不同 key 下，互不影响；request.ts 与各 auth store 共用同一套读写逻辑，避免循环依赖。
const KEYS = {
  admin: { access: 'mydict-admin-access', refresh: 'mydict-admin-refresh' },
  user: { access: 'mydict-user-access', refresh: 'mydict-user-refresh' },
} as const

export type AuthRole = keyof typeof KEYS

// localStorage 本身不是 Vue 响应式来源，直接在 Pinia getter 里读它不会在登录/登出时
// 触发视图更新（要等下次整页刷新）；改成这份 ref 做唯一真源，setTokens/clearTokens
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

export function getRefreshToken(role: AuthRole): string | null {
  return localStorage.getItem(KEYS[role].refresh)
}

export function setTokens(role: AuthRole, accessToken: string, refreshToken: string): void {
  localStorage.setItem(KEYS[role].access, accessToken)
  localStorage.setItem(KEYS[role].refresh, refreshToken)
  loggedInRefs[role].value = true
}

export function clearTokens(role: AuthRole): void {
  localStorage.removeItem(KEYS[role].access)
  localStorage.removeItem(KEYS[role].refresh)
  loggedInRefs[role].value = false
}
