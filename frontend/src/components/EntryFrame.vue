<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useTheme } from '../composables/useTheme'
import ImageLightbox from './ImageLightbox.vue'

const props = defineProps<{
  /**
   * 取回要渲染的词条 HTML 文档。由调用方决定走哪个端点：
   * 前台查询走 /dict/entry、管理端预览走 /admin/dictionaries/{id}/entry、
   * 生词本走 /vocab/{id}/entry（渲染的是收藏时的快照）。
   *
   * 只在挂载时调用一次。内容来源变化时**请用 :key 让组件重建**，不要依赖这个函数
   * 变化去触发重载。
   */
  loader: () => Promise<string>
}>()

const emit = defineEmits<{
  /** 词条正文里点了 entry:// 链接，父级据此发起新查询 */
  entry: [word: string]
  /** 发音的全部候选（mp3 → opus → JS 解码 spx）都放不了 */
  unsupportedAudio: []
}>()

const { resolvedTheme } = useTheme()

// 展开前给一个下限高度，避免 iframe 从 0 高度闪一下
const MIN_HEIGHT = 120
// 上限兜住异常内容；超过才固定在里面滚动。
//
// 取这么大是因为「宁可把页面拉长，也不要在词条里出现滚动条」——用户明确要后者。实测千篇
// 汉语词典的偏旁部首页（80 万字符、1500 多张字形图）渲染出来远超原来 12000 的上限，
// 一被截断就变成词条内部可滚动，看着像高度没有自适应。
const MAX_HEIGHT = 120000
// 4 秒内没收到任何高度上报时的兜底高度（词典脚本先抛错、引导脚本没能装上等）
const FALLBACK_HEIGHT = 320
const FALLBACK_DELAY_MS = 4000
// 增长守卫：内容只增不减地持续变化，说明高度测量与布局在互相触发，冻结成可滚动。
//
// 阈值放宽是因为**图片解码本来就会让高度一路变大**——千篇那类词条里有一千多张字形图，
// 每张解码完都会触发一次上报。按原来的「3 秒后增长 5 次」会把这种正常的加载过程误判成
// 布局震荡，直接冻结成可滚动（又是词条里的滚动条）。
//
// 计数按滚动窗口算（每个窗口 5 秒内超过 40 次才冻结），而不是累计整个生命周期：iframe 折叠后
// 会被保留下来，窗口缩放、词典脚本展开折叠带来的零星增长长期累积，迟早会误触发。
const GROWTH_WINDOW_MS = 5000
const GROWTH_LIMIT = 40
// 单帧消息限流：防止词典脚本往父页刷消息
const MESSAGE_LIMIT = 50
const MESSAGE_WINDOW_MS = 1000

const iframeRef = ref<HTMLIFrameElement | null>(null)
const html = ref('')
// 大图查看器：由 iframe 里的图片点击触发。同一词条有多张大图时带整张表，可以翻页
const lightboxSrc = ref('')
const lightboxAlt = ref('')
const lightboxUrls = ref<string[]>([])
const lightboxIndex = ref(0)
const loading = ref(true)
const failed = ref(false)
const boxHeight = ref(MIN_HEIGHT)
const scrollable = ref(false)

let messageCount = 0
let messageWindowStart = 0
let grew = 0
let growthWindowStart = 0
let firstHeightAt = 0
let frozen = false
let fallbackTimer: number | undefined

function allowMessage(): boolean {
  const now = Date.now()
  if (now - messageWindowStart > MESSAGE_WINDOW_MS) {
    messageWindowStart = now
    messageCount = 0
  }
  messageCount += 1
  return messageCount <= MESSAGE_LIMIT
}

function applyHeight(raw: number) {
  if (!Number.isFinite(raw) || raw <= 0) return
  const now = Date.now()
  if (!firstHeightAt) firstHeightAt = now

  // 只增长不回落 → 冻结，改用滚动，避免页面被无限拉长
  if (now - firstHeightAt > GROWTH_WINDOW_MS && raw > boxHeight.value) {
    if (now - growthWindowStart > GROWTH_WINDOW_MS) {
      growthWindowStart = now
      grew = 0
    }
    grew += 1
    if (grew > GROWTH_LIMIT) {
      frozen = true
      scrollable.value = true
      boxHeight.value = MAX_HEIGHT
      return
    }
  }
  if (frozen) return

  if (raw >= MAX_HEIGHT) {
    boxHeight.value = MAX_HEIGHT
    scrollable.value = true
    return
  }
  // 内容缩回上限以内（如词典脚本折叠了一段）就恢复成不滚动、按内容撑高
  scrollable.value = false
  boxHeight.value = Math.max(MIN_HEIGHT, Math.ceil(raw))
}

/**
 * 打开词条里的外链。postMessage 的内容一律当作不可信输入，只认三种写法：
 * http(s) 链接；词典里常见的 `www.` 裸域名（补成 https）；`mailto:`（交给邮件客户端，
 * 用 location 而不是 window.open，否则会先弹出一个空白标签页）。
 */
function openExternal(raw: string) {
  const url = raw.trim()
  if (/^mailto:/i.test(url)) {
    window.location.href = url
    return
  }
  const normalized = /^www\./i.test(url) ? `https://${url}` : url
  if (!/^https?:\/\//i.test(normalized)) return
  window.open(normalized, '_blank', 'noopener,noreferrer')
}

/**
 * 把当前主题下发给 iframe 里的文档。
 *
 * 子页是不透明源的独立文档，读不到父页的 CSS 变量；它那份暗色样式靠 data-mydict-theme
 * 属性开关，所以主题变化必须由父页通知。
 *
 * 用消息而不是重建 iframe：EntryPanel 特意保留已挂载的 iframe，就是为了折叠再展开时
 * 不丢音频播放位置与内部滚动。
 */
function postTheme() {
  iframeRef.value?.contentWindow?.postMessage(
    { type: 'mydict:cmd', cmd: 'theme', theme: resolvedTheme.value },
    '*',
  )
}

// 主题切换时通知本组件持有的 iframe（每个 iframe 各发各的）
watch(resolvedTheme, postTheme)

function onMessage(event: MessageEvent) {
  const frame = iframeRef.value
  // 用 source 辨认来源：iframe 是不透明源（sandbox 未给 allow-same-origin），
  // 它发出的 event.origin 恒为 "null"，按 origin 判断没有意义。
  if (!frame || event.source !== frame.contentWindow) return
  if (!allowMessage()) return

  const data = event.data as Record<string, unknown> | null
  if (!data || typeof data.type !== 'string') return

  switch (data.type) {
    case 'mydict:ready':
      loading.value = false
      // 子页的 message 监听此时已装好，是下发主题最可靠的时机
      postTheme()
      break
    case 'mydict:height':
      applyHeight(Number(data.height))
      break
    case 'mydict:entry':
      if (typeof data.word === 'string' && data.word.trim()) emit('entry', data.word)
      break
    case 'mydict:open':
      openExternal(String(data.url ?? ''))
      break
    case 'mydict:audio-unsupported':
      emit('unsupportedAudio')
      break
    case 'mydict:image':
      // 扫描版词典（辞海这类）的整页图片在词条里太小，点开用大图查看器看
      if (typeof data.src === 'string' && data.src) {
        lightboxSrc.value = data.src
        lightboxAlt.value = typeof data.alt === 'string' ? data.alt : ''
        lightboxUrls.value = Array.isArray(data.urls)
          ? data.urls.filter((item): item is string => typeof item === 'string' && !!item)
          : [data.src]
        const index = Number(data.index)
        lightboxIndex.value =
          Number.isInteger(index) && index >= 0 && index < lightboxUrls.value.length
            ? index
            : Math.max(0, lightboxUrls.value.indexOf(data.src))
      }
      break
    case 'mydict:audio-error':
      ElMessage.warning('发音播放失败')
      break
    default:
      break
  }
}

async function load() {
  loading.value = true
  failed.value = false
  html.value = ''
  boxHeight.value = MIN_HEIGHT
  scrollable.value = false
  frozen = false
  grew = 0
  growthWindowStart = 0
  firstHeightAt = 0
  try {
    html.value = await props.loader()
  } catch {
    // 具体原因已由响应拦截器提示（401/404 等）
    failed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  window.addEventListener('message', onMessage)
  fallbackTimer = window.setTimeout(() => {
    if (!frozen && boxHeight.value === MIN_HEIGHT) boxHeight.value = FALLBACK_HEIGHT
  }, FALLBACK_DELAY_MS)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('message', onMessage)
  lightboxSrc.value = ''
  lightboxUrls.value = []
  if (fallbackTimer !== undefined) window.clearTimeout(fallbackTimer)
})
</script>

<template>
  <div class="entry-frame">
    <p v-if="failed" class="hint">词条内容加载失败，请重试。</p>
    <p v-else-if="!html" class="hint">正在载入…</p>
    <!--
      sandbox 只给 allow-scripts，**不加** allow-same-origin：两者同时给时，框架内脚本
      能拿到 window.frameElement、摘掉 sandbox 属性后重载自己，等于逃逸。不加
      allow-same-origin 时它是独立的不透明源，既跑得了词典自己的 JS，又碰不到父页面
      （token 存在 localStorage 里）。代价是 localStorage/cookie 等会抛异常，已由
      注入的引导脚本补上内存实现。
    -->
    <iframe
      v-if="html"
      ref="iframeRef"
      class="entry-doc"
      :srcdoc="html"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
      :style="{ height: `${boxHeight}px`, overflow: scrollable ? 'auto' : 'hidden' }"
      title="词条内容"
      @load="postTheme"
    />
    <ImageLightbox
      v-if="lightboxSrc"
      :images="lightboxUrls"
      :index="lightboxIndex"
      :alt="lightboxAlt"
      @navigate="lightboxIndex = $event"
      @close="lightboxSrc = ''"
    />
  </div>
</template>

<style scoped>
.entry-frame {
  width: 100%;
}

.entry-doc {
  display: block;
  width: 100%;
  border: none;
  background: transparent;
}

.hint {
  margin: 0;
  padding: var(--space-3) 0;
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}
</style>
