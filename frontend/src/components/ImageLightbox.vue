<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 词条里点大图后弹出的查看器：滚轮缩放、拖动平移，Esc 或点图片以外的区域退出。
 *
 * 起因是扫描版词典（辞海）——每个词条就是一整页 3383×5184 的扫描图，按容器宽度显示后，
 * 一页上的多栏小字根本读不了，必须能放大了平移着看。
 *
 * 用 `<Teleport to="body">` 而不是就地渲染：EntryFrame 的祖先链上可能有 transform/overflow，
 * 那会让 `position: fixed` 不再相对视口定位、也会被祖先裁剪掉。
 */
const props = defineProps<{ src: string; alt?: string }>()
const emit = defineEmits<{ close: [] }>()

// 单次滚轮的缩放步长系数；deltaY 的量级跨设备差异很大，用指数保证手感一致
const WHEEL_SENSITIVITY = 0.0015
// 相对「适应视口」的缩放上下限
const MIN_ZOOM = 0.5
const MAX_ZOOM = 20
// 超过这个位移才算拖动，否则松手时会被当成「点了空白处」而退出
const DRAG_THRESHOLD = 4

const overlayRef = ref<HTMLElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const failed = ref(false)

let fitScale = 1
let dragging = false
let moved = 0
let pointerStartX = 0
let pointerStartY = 0
let offsetStartX = 0
let offsetStartY = 0
let previousBodyOverflow = ''

function clampScale(next: number) {
  const low = Math.max(fitScale * MIN_ZOOM, 0.01)
  return Math.min(Math.max(next, low), fitScale * MAX_ZOOM)
}

/** 让整张图完整可见，并居中 */
function fitToViewport() {
  const img = imgRef.value
  const overlay = overlayRef.value
  if (!img || !overlay) return
  const naturalWidth = img.naturalWidth || 1
  const naturalHeight = img.naturalHeight || 1
  const viewWidth = overlay.clientWidth
  const viewHeight = overlay.clientHeight
  fitScale = Math.min(viewWidth / naturalWidth, viewHeight / naturalHeight)
  scale.value = fitScale
  offsetX.value = (viewWidth - naturalWidth * fitScale) / 2
  offsetY.value = (viewHeight - naturalHeight * fitScale) / 2
}

/**
 * 缩放时锚定光标：保持光标下方那个图片坐标点不动。
 *
 * 不锚定的话，想放大某处细节时目标会随着缩放跑出视口，等于放大了但看不到想看的地方。
 */
function onWheel(event: WheelEvent) {
  event.preventDefault()
  const overlay = overlayRef.value
  if (!overlay) return
  const rect = overlay.getBoundingClientRect()
  const pointerX = event.clientX - rect.left
  const pointerY = event.clientY - rect.top
  const next = clampScale(scale.value * Math.exp(-event.deltaY * WHEEL_SENSITIVITY))
  const ratio = next / scale.value
  offsetX.value = pointerX - (pointerX - offsetX.value) * ratio
  offsetY.value = pointerY - (pointerY - offsetY.value) * ratio
  scale.value = next
}

function onPointerDown(event: PointerEvent) {
  dragging = true
  moved = 0
  pointerStartX = event.clientX
  pointerStartY = event.clientY
  offsetStartX = offsetX.value
  offsetStartY = offsetY.value
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!dragging) return
  const dx = event.clientX - pointerStartX
  const dy = event.clientY - pointerStartY
  moved = Math.max(moved, Math.abs(dx) + Math.abs(dy))
  offsetX.value = offsetStartX + dx
  offsetY.value = offsetStartY + dy
}

function onPointerUp() {
  dragging = false
}

/** 只有点在图片以外的空白、且刚才没在拖动时才退出 */
function onOverlayClick(event: MouseEvent) {
  if (moved > DRAG_THRESHOLD) return
  if (event.target === overlayRef.value) emit('close')
}

/**
 * 挡住查询页 ←/→ 切换词典的全局监听。
 *
 * HomeView 用 `window.addEventListener('keydown', onKeydown)` 注册在**冒泡阶段**；这里注册在
 * **捕获阶段**的同一个 window 上，捕获先于冒泡执行，`stopImmediatePropagation()` 会让事件
 * 不再往下走，那个监听器就不会被调用。不去改 HomeView，免得两边耦合。
 */
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopImmediatePropagation()
    emit('close')
    return
  }
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault()
    event.stopImmediatePropagation()
  }
}

onMounted(() => {
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  // wheel 必须 passive:false 才能 preventDefault，否则页面会跟着一起滚
  overlayRef.value?.addEventListener('wheel', onWheel, { passive: false })
  window.addEventListener('keydown', onKeydown, true)
})

onBeforeUnmount(() => {
  overlayRef.value?.removeEventListener('wheel', onWheel)
  window.removeEventListener('keydown', onKeydown, true)
  document.body.style.overflow = previousBodyOverflow
})
</script>

<template>
  <Teleport to="body">
    <div
      ref="overlayRef"
      class="lightbox"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @click="onOverlayClick"
    >
      <p v-if="failed" class="lightbox-hint">图片加载失败</p>
      <img
        v-show="!failed"
        ref="imgRef"
        class="lightbox-img"
        :src="props.src"
        :alt="props.alt ?? ''"
        draggable="false"
        :style="{
          transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
        }"
        @load="fitToViewport"
        @error="failed = true"
      />
      <p class="lightbox-hint">滚轮缩放 · 拖动移动 · Esc 或点空白处退出</p>
    </div>
  </Teleport>
</template>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 3000;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.86);
  /* 扫描图上小字密集，放大后要尽量保持锐利 */
  touch-action: none;
  cursor: grab;
}

.lightbox:active {
  cursor: grabbing;
}

.lightbox-img {
  position: absolute;
  top: 0;
  left: 0;
  /* 变换以左上角为基准，平移量才能按「图片左上角在视口里的位置」直接算 */
  transform-origin: 0 0;
  max-width: none;
  user-select: none;
  -webkit-user-drag: none;
}

.lightbox-hint {
  position: absolute;
  bottom: var(--space-4);
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-lg);
  background: rgba(0, 0, 0, 0.55);
  color: #f2f5f4;
  font-size: var(--text-sm);
  pointer-events: none;
}
</style>
