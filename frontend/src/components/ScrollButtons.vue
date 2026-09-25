<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { prefersReducedMotion } from '../utils/motion'

// 滚动动画时长。比参考实现固定的 300ms 更短一点，长页面来回跳时不容易等得不耐烦。
const SCROLL_DURATION_MS = 300
// 滚动超过这个距离才出现按钮；距底部不足这个距离就单独隐藏「回到底部」
const VISIBILITY_THRESHOLD = 200

const visible = ref(false)
const atBottom = ref(false)
const maxScrollTop = ref(0)

let rafId = 0
// 滚动事件只用来置位，真正的测量合并到一帧里做，避免每个事件都读一次 scrollHeight
let ticking = false
let resizeObserver: ResizeObserver | undefined

function currentScrollTop(): number {
  return window.pageYOffset || document.documentElement.scrollTop || 0
}

function computeMaxScrollTop(): number {
  return Math.max(0, document.documentElement.scrollHeight - window.innerHeight)
}

function update() {
  const top = currentScrollTop()
  const max = computeMaxScrollTop()
  maxScrollTop.value = max
  visible.value = top >= VISIBILITY_THRESHOLD
  atBottom.value = max - top < VISIBILITY_THRESHOLD
}

function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => {
    ticking = false
    update()
  })
}

function animateTo(targetTop: number) {
  // 连点会叠加多个动画，先掐掉上一个
  cancelAnimationFrame(rafId)

  // 先夹到合法范围再算位移：直接拿 scrollHeight 当目标会算出超出实际的 delta
  const target = Math.min(Math.max(0, targetTop), computeMaxScrollTop())
  const start = currentScrollTop()
  const delta = target - start
  if (Math.abs(delta) < 1 || prefersReducedMotion()) {
    window.scrollTo(0, target)
    return
  }

  const startTime = performance.now()
  const step = (now: number) => {
    const progress = Math.min((now - startTime) / SCROLL_DURATION_MS, 1)
    // easeOutCubic
    const eased = 1 - Math.pow(1 - progress, 3)
    window.scrollTo(0, start + delta * eased)
    if (progress < 1) rafId = requestAnimationFrame(step)
  }
  rafId = requestAnimationFrame(step)
}

function onKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  // 输入框里的 Home/End 是在移动光标，不能抢
  if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) {
    return
  }
  if (event.key === 'Home') {
    event.preventDefault()
    animateTo(0)
  } else if (event.key === 'End') {
    event.preventDefault()
    animateTo(maxScrollTop.value)
  }
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onScroll)
  // 词条 iframe 是异步长高的，展开/折叠词典也会改页面高度。
  // 只监听 scroll/resize 的话，按钮显隐会滞后到用户下次滚动为止。
  resizeObserver = new ResizeObserver(update)
  resizeObserver.observe(document.documentElement)
  update()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onScroll)
  resizeObserver?.disconnect()
  cancelAnimationFrame(rafId)
})
</script>

<template>
  <div class="scroll-nav" :class="{ 'scroll-nav-hidden': !visible }">
    <button type="button" class="scroll-btn" aria-label="回到顶部" @click="animateTo(0)">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 5l-7 7 1.4 1.4L11 8.8V20h2V8.8l4.6 4.6L19 12z" />
      </svg>
    </button>
    <button
      v-show="!atBottom"
      type="button"
      class="scroll-btn"
      aria-label="回到底部"
      @click="animateTo(maxScrollTop)"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 19l7-7-1.4-1.4L13 15.2V4h-2v11.2l-4.6-4.6L5 12z" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.scroll-nav {
  position: fixed;
  right: var(--space-4);
  bottom: var(--space-5);
  /* 高于页面内容，但要低于移动端抽屉（10/20）与 Element Plus 浮层（2000+） */
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  transition:
    opacity var(--motion-duration-base) var(--motion-ease-standard),
    visibility var(--motion-duration-base) var(--motion-ease-standard);
}

.scroll-nav-hidden {
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}

.scroll-btn {
  width: var(--size-control-lg);
  height: var(--size-control-lg);
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  /* 半透明 + 毛玻璃：浮在词条正文上时不至于把内容整块切掉 */
  background: color-mix(in srgb, var(--color-bg-surface-raised) 92%, transparent);
  backdrop-filter: blur(6px);
  color: var(--color-text-secondary);
  box-shadow: var(--shadow-elevation-1);
  cursor: pointer;
  transition: all var(--motion-duration-fast) var(--motion-ease-standard);
}

.scroll-btn:hover {
  border-color: var(--color-border-hover);
  background: var(--color-bg-surface-raised);
  box-shadow: var(--shadow-elevation-2);
  color: var(--color-text-primary);
  transform: scale(1.05);
}

.scroll-btn svg {
  /* 一次性取值：箭头图标在 44px 圆按钮里取约三分之一，视觉上最均衡 */
  width: 15px;
  height: 15px;
  fill: currentColor;
}

@media (max-width: 640px) {
  .scroll-nav {
    right: var(--space-3);
    bottom: var(--space-4);
  }

  /* 一次性取值：窄屏上给正文让出更多宽度，38px 是仍能稳定点中的下限 */
  .scroll-btn {
    width: 38px;
    height: 38px;
  }
}
</style>
