/**
 * 用户是否要求减少动效（系统级「减少动态效果」设置）。
 *
 * 取不到 matchMedia 时按「不减少」处理：这是无障碍偏好，读不到就不该擅自把动效关掉。
 */
export function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}
