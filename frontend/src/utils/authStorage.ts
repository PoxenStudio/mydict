// 管理员/用户 Token 分别存储在不同 key 下，互不影响；request.ts 与各 auth store 共用同一套读写逻辑，避免循环依赖。
const KEYS = {
  admin: { access: 'mydict-admin-access', refresh: 'mydict-admin-refresh' },
  user: { access: 'mydict-user-access', refresh: 'mydict-user-refresh' },
} as const

export type AuthRole = keyof typeof KEYS

export function getAccessToken(role: AuthRole): string | null {
  return localStorage.getItem(KEYS[role].access)
}

export function getRefreshToken(role: AuthRole): string | null {
  return localStorage.getItem(KEYS[role].refresh)
}

export function setTokens(role: AuthRole, accessToken: string, refreshToken: string): void {
  localStorage.setItem(KEYS[role].access, accessToken)
  localStorage.setItem(KEYS[role].refresh, refreshToken)
}

export function clearTokens(role: AuthRole): void {
  localStorage.removeItem(KEYS[role].access)
  localStorage.removeItem(KEYS[role].refresh)
}
