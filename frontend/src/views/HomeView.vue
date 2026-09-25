<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import NavBar from '../components/NavBar.vue'
import DictionarySidebar from '../components/DictionarySidebar.vue'
import EntryPanel from '../components/EntryPanel.vue'
import SkeletonList from '../components/SkeletonList.vue'
import EmptyState from '../components/EmptyState.vue'
import { searchWord } from '../api/dict'
import { getSystemInfo } from '../api/system'
import { useUserAuthStore } from '../stores/userAuth'
import { useSettingsStore } from '../stores/settings'
import { useFavorites } from '../composables/useFavorites'
import { useDictionaryFilter } from '../composables/useDictionaryFilter'
import { prefersReducedMotion } from '../utils/motion'
import type { QueryResultItem } from '../types/query'

const router = useRouter()
const route = useRoute()
const authStore = useUserAuthStore()
const settingsStore = useSettingsStore()
const { favoriteMap, favoriteLoading, loadFavorites, toggleFavorite } = useFavorites()
const {
  dictionaries,
  selectedIds,
  checkedIds,
  allIds,
  filterIds,
  isFiltering,
  loading: dictLoading,
  load: loadDictionaryFilter,
  toggle: toggleDictionary,
  setSelection,
  selectAllOrClear,
} = useDictionaryFilter()

// 同时保留的 iframe 文档数上限：折叠时不立刻销毁（声音还在放、内部滚动位置也要留住），
// 但也不能无限累积——一次查询最多可能命中几十部词典，每个 iframe 都是一份带 CSS/JS 的文档。
const MAX_LIVE_FRAMES = 5

const word = ref('')
const submittedWord = ref('')
const results = ref<QueryResultItem[]>([])
const resultsRef = ref<HTMLElement | null>(null)
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const version = ref('')
const mobileOpen = ref(false)

// 展开状态只存一个 key（互斥展开）；liveKeys 是「已挂载过 iframe」的 LRU 列表
const expandedKey = ref<string | null>(null)
const liveKeys = ref<string[]>([])

const showLoginGate = computed(
  () => settingsStore.loaded && !settingsStore.openAccess && !authStore.isLoggedIn,
)

const favoritedWords = computed(() => new Set(favoriteMap.value.keys()))

interface DictionaryGroup {
  key: string
  dictionaryId: number
  dictionaryName: string
  entries: QueryResultItem[]
}

// 按词典分组。同一部词典命中多条（同形不同大小写、或以后查询扩展带来的多个词形）合并成一张面板，
// 面板顺序沿用后端给的顺序——后端已按「优先语言优先、再按 sort_order」排好。
const groups = computed<DictionaryGroup[]>(() => {
  const map = new Map<number, DictionaryGroup>()
  for (const item of results.value) {
    let group = map.get(item.dictionary_id)
    if (!group) {
      group = {
        key: String(item.dictionary_id),
        dictionaryId: item.dictionary_id,
        dictionaryName: item.dictionary_name,
        entries: [],
      }
      map.set(item.dictionary_id, group)
    }
    group.entries.push(item)
  }
  return [...map.values()]
})

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  getSystemInfo()
    .then((info) => {
      version.value = info.version
    })
    .catch(() => undefined)
  if (!settingsStore.loaded) await settingsStore.load().catch(() => undefined)
  if (settingsStore.loaded && !settingsStore.initialized) {
    router.replace('/admin/setup')
    return
  }
  // 收藏与词典列表各自容错：任一失败都不该把后面的「外链直达」带下去。
  // 这里是裸 Promise.all 的话，loadFavorites 在未登录等场景下一 reject，
  // runFromUrl() 就永远不执行——表现为打开 /?q=词 输入框空着、毫无反应，
  // 而且异常发生在 async 回调里，只会变成一条 unhandled rejection，很难查。
  await Promise.all([loadFavorites().catch(() => undefined), loadDictionaryFilter()])
  // 词典列表与登录态都就绪了，这时才处理地址栏里的 ?q=（外链直达）
  await runFromUrl()
})

// 检索范围变了就用新范围重查（还没查过就不动）。比的是勾选结果的字符串，这样从
// [1,2] 换成 [1,3] 这种数量不变的变化也能触发。
watch(
  () => selectedIds.value.join(','),
  () => {
    if (submittedWord.value) runSearch()
  },
)

// 侧边栏语言按钮传来的「筛选范围」→ 对应的 lang_from 取值。
// 「zh」（中文）覆盖简繁与早期数据里的裸 zh：查询路由本来就不区分它们（输入汉字时三种码
// 都算优先语言），所以这里也不该让用户为简繁多点一次。
const LANGUAGE_SCOPE_CODES: Record<string, string[]> = {
  zh: ['zh', 'zh-Hans', 'zh-Hant'],
}

/** 侧边栏的「只看某种语言」：勾选该筛选范围下的全部词典 */
function selectLanguage(scope: string) {
  const codes = LANGUAGE_SCOPE_CODES[scope] ?? [scope]
  setSelection(
    dictionaries.value.filter((item) => codes.includes(item.lang_from)).map((i) => i.id),
  )
}

function touchLive(key: string) {
  liveKeys.value = [key, ...liveKeys.value.filter((k) => k !== key)].slice(0, MAX_LIVE_FRAMES)
}

// 与 EntryPanel 里 .panel 的 scroll-margin-top 保持一致
const PANEL_SCROLL_OFFSET = 16
// 展开词典时把标题滚到顶部的动画时长
const PANEL_SCROLL_DURATION_MS = 500

let panelScrollRaf = 0

function findPanel(key: string): HTMLElement | null {
  return resultsRef.value?.querySelector<HTMLElement>(`[data-dict-key="${key}"]`) ?? null
}

/** 「面板顶部对齐到视口顶部」对应的滚动位置 */
function panelScrollTarget(panel: HTMLElement): number {
  return Math.max(0, panel.getBoundingClientRect().top + window.scrollY - PANEL_SCROLL_OFFSET)
}

/**
 * 把某部词典的面板平滑滚到视口顶部。
 *
 * 自己补间，而不是用 scrollIntoView({ behavior: 'smooth' })：展开会连着引起两次布局剧变
 * （上一部词典折叠、这一部的 iframe 从兜底高度跳到真实高度），浏览器会把平滑滚动中途掐断、
 * 停在半路。自己补间时每帧都重算一次目标位置，布局怎么变都跟得上，也不会被掐断。
 */
function scrollPanelToTop(key: string) {
  const panel = findPanel(key)
  if (!panel) return
  cancelAnimationFrame(panelScrollRaf)

  const startY = window.scrollY
  const target = panelScrollTarget(panel)
  if (prefersReducedMotion() || Math.abs(target - startY) < 1) {
    window.scrollTo(0, target)
    return
  }

  const startAt = performance.now()
  const step = (now: number) => {
    const progress = Math.min((now - startAt) / PANEL_SCROLL_DURATION_MS, 1)
    // easeOutCubic
    const eased = 1 - Math.pow(1 - progress, 3)
    window.scrollTo(0, startY + (panelScrollTarget(panel) - startY) * eased)
    if (progress < 1) panelScrollRaf = requestAnimationFrame(step)
  }
  panelScrollRaf = requestAnimationFrame(step)
}

function toggleGroup(key: string) {
  if (expandedKey.value === key) {
    // 折叠不滚动：收起内容不会把别的东西挤走
    expandedKey.value = null
    return
  }
  expandedKey.value = key
  touchLive(key)
  // 展开的词典可能在视口之外——前面那部词典的长词条把后面的全挤出屏幕了，此时它的标题
  // 连同正文都落在视口外。把标题滚到视口顶部，正文就正好从顶部开始读。
  // 只在这条路径上滚：runSearch 的自动展开不能滚，否则查询完页面立刻被拽走。
  nextTick(() => scrollPanelToTop(key))
}

/**
 * 方向键切换展开的词典：← 上一部，→ 下一部。
 *
 * 到头就不动——按着不放时绕回另一端会让视口反复横跳。当前没有展开的词典时，→ 从第一部开始。
 */
function moveExpanded(delta: number) {
  const keys = groups.value.map((group) => group.key)
  if (!keys.length) return
  const index = expandedKey.value ? keys.indexOf(expandedKey.value) : -1
  const next = index === -1 ? (delta > 0 ? 0 : -1) : index + delta
  if (next < 0 || next >= keys.length) return
  const key = keys[next]
  expandedKey.value = key
  touchLive(key)
  nextTick(() => scrollPanelToTop(key))
}

function onKeydown(event: KeyboardEvent) {
  if (event.ctrlKey || event.altKey || event.metaKey) return
  // 输入框里的方向键是在移动光标，不能抢
  const target = event.target as HTMLElement | null
  if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) {
    return
  }
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    moveExpanded(-1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    moveExpanded(1)
  }
}

// 组件卸载后别让补间继续跑
onBeforeUnmount(() => {
  cancelAnimationFrame(panelScrollRaf)
  window.removeEventListener('keydown', onKeydown)
})

async function runSearch(query?: string) {
  const q = (query ?? word.value).trim()
  if (!q) return
  if (showLoginGate.value) return

  word.value = q
  status.value = 'loading'
  submittedWord.value = q
  try {
    const resp = await searchWord(q, filterIds.value)
    results.value = resp.results
    status.value = 'ok'
    // 结果出来后把词同步进地址栏，链接才能分享、刷新才能复现
    syncQueryToUrl(q)
    // 排序第一的那部词典默认展开，其余折叠
    const first = resp.results[0]
    expandedKey.value = first ? String(first.dictionary_id) : null
    liveKeys.value = first ? [String(first.dictionary_id)] : []
  } catch {
    status.value = 'error'
  }
}

/**
 * 把当前查询词写进地址栏的 `?q=`。
 *
 * 用 `replace` 而不是 `push`：每查一个词就压一条历史的话，浏览器后退键很快就被查询记录塞满，
 * 而这里的历史价值只是「能分享、刷新能复现」。值没变时不碰路由，免得白触发一次导航。
 */
function syncQueryToUrl(q: string) {
  if (String(route.query.q ?? '') === q) return
  router.replace({ query: q ? { q } : {} })
}

/**
 * 外链直达：`/?q=词` 打开就查。
 *
 * 浏览器地址栏关键字（URL 模板填 `.../?q=%s`）、书签小工具、以及任何能拼 URL 的地方都靠它。
 * 未登录时不能直接查（runSearch 会被登录墙挡掉），所以把词留在输入框里并说明原因——
 * 否则用户点开链接看到的是空页面，会以为链接坏了。
 */
async function runFromUrl() {
  const initial = String(route.query.q ?? '').trim()
  if (!initial) return
  word.value = initial
  if (showLoginGate.value) {
    ElMessage.info('请先登录后再查询')
    return
  }
  try {
    await runSearch(initial)
  } catch {
    // runSearch 内部已经吃了查询本身的异常（会把状态置成 error），这里只是兜住
    // 「连查询都没发起就抛了」的意外，别让它变成静默的 unhandled rejection
    status.value = 'error'
  }
}

/** iframe 里点了 entry:// 词条链接，按新词重查 */
function searchFromEntry(next: string) {
  if (next.trim() === submittedWord.value.trim()) {
    // 静默 return 会让用户以为「点了没反应」——选中当前词条里的文字点【查词】就是这种情况
    ElMessage.info('当前已在显示该词条')
    return
  }
  runSearch(next)
}

function onUnsupportedAudio() {
  ElMessage.warning('这条发音不存在或解码失败，暂时无法播放')
}
</script>

<template>
  <div class="page">
    <NavBar />

    <main class="search-page">
      <section class="search-head">
        <form class="search-box" :class="{ disabled: showLoginGate }" @submit.prevent="runSearch()">
          <input
            v-model="word"
            type="text"
            placeholder="输入要查询的单词或词语"
            :disabled="showLoginGate"
          />
          <button type="submit" :disabled="showLoginGate">查询</button>
        </form>
      </section>

      <div class="sidebar-slot">
        <button type="button" class="sidebar-toggle" @click="mobileOpen = true">
          检索范围（{{ checkedIds.size }}/{{ allIds.length }}）
        </button>
        <DictionarySidebar
          :dictionaries="dictionaries"
          :checked-ids="checkedIds"
          :loading="dictLoading"
          :is-filtering="isFiltering"
          :mobile-open="mobileOpen"
            @toggle="toggleDictionary"
            @select-all="selectAllOrClear"
          @select-language="selectLanguage"
          @close-mobile="mobileOpen = false"
        />
      </div>

      <div class="layout">
        <div class="content">
          <div v-if="showLoginGate" class="login-gate">
            <p>
              当前需要登录才能查询，<router-link to="/login">立即登录</router-link> 或
              <router-link to="/register">注册账号</router-link>。
            </p>
          </div>

          <SkeletonList v-else-if="status === 'loading'" :rows="2" />

          <EmptyState
            v-else-if="status === 'error'"
            title="网络异常，请重试"
            action-text="重新查询"
            @action="runSearch()"
          />

          <EmptyState
            v-else-if="status === 'ok' && results.length === 0"
            :title="`暂未收录「${submittedWord}」，欢迎联系管理员补充词典`"
          />

          <div v-else-if="status === 'ok'" ref="resultsRef" class="results">
            <EntryPanel
              v-for="group in groups"
              :key="group.key"
              :data-dict-key="group.key"
              :dictionary-name="group.dictionaryName"
              :entries="group.entries"
              :query-word="submittedWord"
              :expanded="expandedKey === group.key"
              :mounted="liveKeys.includes(group.key)"
              :favorited-words="favoritedWords"
              :favorite-loading="favoriteLoading"
              @toggle="toggleGroup(group.key)"
              @entry="searchFromEntry"
              @toggle-favorite="toggleFavorite"
              @unsupported-audio="onUnsupportedAudio"
            />
          </div>
        </div>
      </div>
    </main>

    <footer class="site-footer">
      <h1 class="tagline">{{ settingsStore.siteName }} · 查询与生词本</h1>
      <p v-if="authStore.isLoggedIn" class="search-hint">{{ settingsStore.searchHintText }}</p>
      <p class="search-hint">Ver: {{ version ? version : '0.0.0' }}</p>
      <p class="search-hint">
        <router-link class="footer-link" to="/admin">管理后台</router-link>
      </p>
    </footer>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg-base);
}

/* 两列栅格：左列是检索范围，右列上方是查询框、下方是结果。
   检索范围跨两行，这样往下滚读词条时它能一直粘在视口里。 */
.search-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: var(--space-7) var(--space-4);
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  /* 第一行按搜索框的实际高度，其余空间全给第二行：
     检索范围卡片比查词结果高时，跨两行的它会把两个 auto 行一起拉高（多出来的高度
     平分给两行），结果区就被推到搜索框下方很远处，看着像「垂直居中」。 */
  grid-template-rows: auto 1fr;
  gap: var(--space-5);
  align-items: start;
}

.search-head {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.sidebar-slot {
  grid-column: 1;
  grid-row: 1 / span 2;
  position: sticky;
  top: var(--space-5);
}

.layout {
  grid-column: 2;
  grid-row: 2;
  min-width: 0;
}

.sidebar-toggle {
  display: none;
}

.content {
  min-width: 0;
}

.tagline {
  text-align: center;
  font-size: var(--text-lg);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin: 0;
}

/* 站名、提示语与版本号统一收在页脚，查询区只留一个搜索框 */
.site-footer {
  max-width: 1180px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4) var(--space-7);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.footer-link {
  color: var(--color-brand-500);
  text-decoration: none;
}

.footer-link:hover {
  text-decoration: underline;
}

.search-box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-bg-surface);
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-5);
  border: 1px solid transparent;
}

.search-box:focus-within {
  box-shadow: var(--shadow-elevation-2);
  border-color: var(--color-brand-500);
}

.search-box.disabled {
  opacity: 0.6;
}

.search-box input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  height: 48px;
  font-size: var(--text-md);
  color: var(--color-text-primary);
}

.search-box button {
  height: 40px;
  padding: 0 var(--space-5);
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: #fff;
  font-size: var(--text-base);
  cursor: pointer;
}

.search-box button:hover {
  background: var(--color-brand-600);
}

.search-box button:disabled {
  background: var(--color-border);
  cursor: not-allowed;
}

.search-hint {
  margin: 0;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.login-gate {
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.results {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

@media (max-width: 640px) {
  /* 窄屏回落成单列：查询框在前，检索范围（这时只剩抽屉入口）居中，结果在最后 */
  .search-page {
    grid-template-columns: minmax(0, 1fr);
  }

  .search-head {
    grid-column: 1;
    grid-row: 1;
  }

  .sidebar-slot {
    grid-column: 1;
    grid-row: 2;
    position: static;
  }

  .layout {
    grid-column: 1;
    grid-row: 3;
  }

  .sidebar-toggle {
    display: block;
    width: 100%;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
    font-size: var(--text-sm);
    padding: var(--space-2);
    cursor: pointer;
  }
}
</style>
