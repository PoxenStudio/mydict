<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import NavBar from '../components/NavBar.vue'
import SystemTaskBanner from '../components/SystemTaskBanner.vue'
import DictionaryScopePanel from '../components/DictionaryScopePanel.vue'
import EntryPanel from '../components/EntryPanel.vue'
import OnlineDictPanel from '../components/OnlineDictPanel.vue'
import RandomDictPanel from '../components/RandomDictPanel.vue'
import SkeletonList from '../components/SkeletonList.vue'
import EmptyState from '../components/EmptyState.vue'
import { searchWord } from '../api/dict'
import { langLabel } from '../utils/language'
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
  clearedView,
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
// 检索范围面板默认收起，只露出一行摘要
const scopeOpen = ref(false)

// 展开状态只存一个 key（互斥展开）；liveKeys 是「已挂载过 iframe」的 LRU 列表
const expandedKey = ref<string | null>(null)
const liveKeys = ref<string[]>([])

const showLoginGate = computed(
  () => settingsStore.loaded && !settingsStore.openAccess && !authStore.isLoggedIn,
)

// 检索范围只给登录用户：列出的是其「可用词典」，访客（开放使用）直接查全部已启用词典
const showScope = computed(() => authStore.isLoggedIn)

const scopeSummary = computed(() => {
  if (onlineMode.value) return '在线词典'
  if (randomMode.value) return '随机浏览'
  if (dictLoading.value) return '载入中…'
  if (!isFiltering.value) return `全部词典（${allIds.value.length}）`
  return `已选 ${checkedIds.value.size} / ${allIds.value.length} 部`
})

// 在「词典选择」里改了可用词典后，检索范围跟着换成新的列表
watch(
  () => (authStore.profile ? (authStore.profile.allowed_dictionary_ids ?? []).join(',') : null),
  (current, previous) => {
    // previous 为 null 是个人资料刚加载完，不是用户改了设置
    if (showScope.value && previous !== null && current !== previous) loadDictionaryFilter()
  },
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
  await Promise.all([
    loadFavorites().catch(() => undefined),
    authStore.isLoggedIn ? loadDictionaryFilter() : undefined,
  ])
  // 词典列表与登录态都就绪了，这时才处理地址栏里的 ?q=（外链直达）
  await runFromUrl()
})

// 检索范围变了就用新范围重查（还没查过就不动）。比的是勾选结果的字符串，这样从
// [1,2] 换成 [1,3] 这种数量不变的变化也能触发。
watch(
  () => selectedIds.value.join(','),
  () => {
    // 随机模式下勾选变化只换池子（RandomDictPanel 自己 watch poolIds），不发查询
    if (onlineMode.value || randomMode.value) return
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
  onlineMode.value = false
  randomMode.value = false
  const codes = LANGUAGE_SCOPE_CODES[scope] ?? [scope]
  setSelection(
    dictionaries.value.filter((item) => codes.includes(item.lang_from)).map((i) => i.id),
  )
}

// --- 在线词典模式 ---
// 【在线】打开后，查询不再走本地词典库，而是服务端代理去查维基百科/维基词典/百度百科，
// 并给出 Google 等外部搜索链接。任何本地范围的选择（语言标签/全部/勾选）都会退出该模式。
const onlineMode = ref(false)

/** 侧栏勾选态：在线模式下本地词典都不参与，显示为全不勾（原勾选保留在 selectedIds，切回即恢复） */
const sidebarCheckedIds = computed(() =>
  onlineMode.value ? new Set<number>() : checkedIds.value,
)

// --- 检索范围标签行（常驻在搜索框下方，不受折叠面板影响） ---
// 从 DictionaryScopePanel 迁出：语言/在线切换是高频操作，不该藏在折叠面板里；
// 面板只留「挑具体词典」这个低频动作。

// 中文系（含早期数据里的裸 zh）在界面上合成一个按钮：查询路由本来就不区分简繁
// （输入汉字时三种码都算「优先语言」），拆成两个按钮只会让「只看中文词典」要点两次。
// ZH_CODES 与词典管理页的语种 tab 共用同一份定义，避免两处各写一遍。
// 中文按钮的循环顺序：中文（全部）→ 简中 → 繁中 → 中文…
const ZH_SCOPES = ['zh', 'zh-Hans', 'zh-Hant']
const ZH_SCOPE_LABELS: Record<string, string> = {
  zh: '中文',
  'zh-Hans': '简中',
  'zh-Hant': '繁中',
}

/** 每个筛选范围对应的 lang_from 取值；不在表里的按原样精确匹配 */
const SCOPE_CODES: Record<string, string[]> = {
  zh: ['zh', 'zh-Hans', 'zh-Hant'],
  'zh-Hans': ['zh-Hans'],
  'zh-Hant': ['zh-Hant'],
}

/** 库里出现过的语言筛选项，按出现顺序去重；中文系合并成一项 */
const languageScopes = computed(() => {
  const scopes: string[] = []
  let zhAdded = false
  for (const item of dictionaries.value) {
    const code = item.lang_from
    if (SCOPE_CODES.zh.includes(code)) {
      if (!zhAdded) {
        zhAdded = true
        scopes.push('zh')
      }
      continue
    }
    if (!scopes.includes(code)) scopes.push(code)
  }
  return scopes
})

/** 当前勾选集是否恰好等于某个筛选范围的全部词典 */
function matchesScope(scope: string): boolean {
  const codes = SCOPE_CODES[scope] ?? [scope]
  const ids = dictionaries.value
    .filter((item) => codes.includes(item.lang_from))
    .map((item) => item.id)
  return (
    ids.length > 0 &&
    ids.length === checkedIds.value.size &&
    ids.every((id) => checkedIds.value.has(id))
  )
}

/** 中文按钮当前落在哪一态；不在任何一种中文范围里时为 null（按钮显示默认的「中文」） */
const activeZhScope = computed<string | null>(() => {
  if (!isFiltering.value) return null
  for (const scope of ZH_SCOPES) {
    if (matchesScope(scope)) return scope
  }
  return null
})

function scopeLabel(scope: string): string {
  return scope === 'zh' ? ZH_SCOPE_LABELS[activeZhScope.value ?? 'zh'] : langLabel(scope)
}

/** 标签行当前亮起的按钮：在线/随机各自独占，本地模式下亮「全部」或命中的语言 */
const activeTab = computed<string>(() => {
  if (onlineMode.value) return 'online'
  if (randomMode.value) return 'random'
  if (!isFiltering.value) return 'all'
  for (const scope of languageScopes.value) {
    if (matchesScope(scope)) return scope
  }
  return ''
})

function selectScope(scope: string) {
  if (scope !== 'zh') {
    selectLanguage(scope)
    return
  }
  // 中文按钮：在三种范围之间循环
  const index = activeZhScope.value ? ZH_SCOPES.indexOf(activeZhScope.value) : -1
  selectLanguage(ZH_SCOPES[(index + 1) % ZH_SCOPES.length])
}

function selectOnline() {
  // 面板自治：挂载/ watch word 时自己发起请求
  onlineMode.value = true
  randomMode.value = false
}

// --- 随机浏览 ---
// 以当前检索范围勾选的词典为池，每次【换一个】随机挑一条展示。任何本地范围
// 的选择（语言标签/全部/勾选）会换池子但不退出随机模式；发起正常查询才退出。
const randomMode = ref(false)

const randomPool = computed(() => (isFiltering.value ? filterIds.value ?? [] : allIds.value))

function selectRandom() {
  onlineMode.value = false
  randomMode.value = true
}

// 本地范围选择（勾选/全部/不选）会退出在线模式；随机模式换池子但不退出
function onToggleDict(id: number) {
  onlineMode.value = false
  randomMode.value = false
  toggleDictionary(id)
}

function onSelectAll() {
  onlineMode.value = false
  randomMode.value = false
  selectAllOrClear()
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

  // 发起正常查询 = 明确要检索，退出随机模式
  randomMode.value = false

  word.value = q
  if (onlineMode.value) {
    // 在线模式：结果区域交给 OnlineDictPanel 自己拉取（它 watch word）
    submittedWord.value = q
    syncQueryToUrl(q)
    return
  }
  onlineMode.value = false
  status.value = 'loading'
  submittedWord.value = q
  try {
    const resp = await searchWord(q, showScope.value ? filterIds.value : undefined)
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

/** 分批切换后把面板滚回顶部（与展开时的滚动同款） */
function onRescroll(key: string) {
  nextTick(() => scrollPanelToTop(key))
}
</script>

<template>
  <div class="page">
    <NavBar />
    <SystemTaskBanner />

    <main class="search-page">
      <section class="search-head">
        <h1 class="tagline">{{ settingsStore.siteName }} · 查询与生词本</h1>
        <form class="search-box" :class="{ disabled: showLoginGate }" @submit.prevent="runSearch()">
          <input
            v-model="word"
            type="text"
            placeholder="输入要查询的单词或词语"
            :disabled="showLoginGate"
          />
          <button type="submit" :disabled="showLoginGate">查询</button>
        </form>

        <!--
          检索范围标签行：语言/在线切换是高频操作，常驻搜索框下方（不随下面的
          词典列表面板折叠）。点任何本地范围都会退出在线模式。
        -->
        <div v-if="showScope" class="scope-tabs">
          <button
            type="button"
            :class="{ active: activeTab === 'all' }"
            @click="onSelectAll"
          >
            {{ clearedView ? '不选' : '全部' }}
          </button>
          <button
            v-for="scope in languageScopes"
            :key="scope"
            type="button"
            :class="{ active: activeTab === scope }"
            @click="selectScope(scope)"
          >
            {{ scopeLabel(scope) }}
          </button>
          <!-- 总开关（管理后台默认禁用）：关着时连标签都不出现 -->
          <button
            v-if="settingsStore.onlineDictEnabled"
            type="button"
            :class="{ active: onlineMode }"
            @click="selectOnline"
          >
            在线
          </button>
          <!-- 随机浏览：池子 = 当前检索范围勾选的词典 -->
          <button
            type="button"
            :class="{ active: randomMode }"
            @click="selectRandom"
          >
            随机
          </button>
        </div>

        <!--
          折叠的词典列表：低频的「挑具体词典」动作。在线模式下没有本地词典可选，
          整行（含开关）藏掉，只剩标签行。
        -->
        <div v-if="showScope && !onlineMode" class="scope">
          <button
            type="button"
            class="scope-toggle"
            :aria-expanded="scopeOpen"
            aria-controls="dictionary-scope-panel"
            @click="scopeOpen = !scopeOpen"
          >
            <span>检索范围：{{ scopeSummary }}</span>
            <el-icon class="scope-arrow" :class="{ open: scopeOpen }"><ArrowRight /></el-icon>
          </button>
          <DictionaryScopePanel
            v-show="scopeOpen"
            id="dictionary-scope-panel"
            :dictionaries="dictionaries"
            :checked-ids="sidebarCheckedIds"
            :loading="dictLoading"
            @toggle="onToggleDict"
          />
        </div>
      </section>

      <div class="layout">
        <div class="content">
          <div v-if="showLoginGate" class="login-gate">
            <p>
              当前需要登录才能查询，<router-link to="/login">立即登录</router-link> 或
              <router-link to="/register">注册账号</router-link>。
            </p>
          </div>

          <template v-else-if="randomMode">
            <!-- 随机浏览：池子 = 当前检索范围勾选的词典 -->
            <RandomDictPanel
              :pool-ids="randomPool"
              :favorited-words="favoritedWords"
              :favorite-loading="favoriteLoading"
              @entry="searchFromEntry"
              @toggle-favorite="toggleFavorite"
              @unsupported-audio="onUnsupportedAudio"
            />
          </template>

          <template v-else-if="onlineMode">
            <!-- 面板自治：加载/错误/结果都在内部渲染，:key 保证换词重新发起查询 -->
            <OnlineDictPanel :key="submittedWord" :word="submittedWord" />
          </template>

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
              @rescroll="onRescroll(group.key)"
            />
          </div>
        </div>
      </div>
    </main>

    <footer class="site-footer">
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

/* 单列居中：标题、搜索框、检索范围（默认收起）自上而下，结果列表在最后 */
.search-page {
  max-width: var(--size-content-md);
  margin: 0 auto;
  padding: var(--space-7) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.search-head {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.layout,
.content {
  min-width: 0;
}

.scope {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.scope-toggle {
  align-self: center;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  border: none;
  border-radius: var(--radius-full);
  background: transparent;
  padding: var(--space-1) var(--space-3);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.scope-toggle:hover {
  background: var(--color-hover-tint);
  color: var(--color-text-primary);
}

.scope-arrow {
  transition: transform 0.2s ease;
}

.scope-arrow.open {
  transform: rotate(90deg);
}

/* 检索范围标签行：常驻搜索框下方（高频操作），样式沿用原面板 actions 的胶囊按钮 */
.scope-tabs {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-2);
}

.scope-tabs button {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-bg-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}

.scope-tabs button:hover {
  border-color: var(--color-border-hover);
  background: var(--color-hover-tint);
}

.scope-tabs button.active {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
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
  max-width: var(--size-content-md);
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

/* 浅色主题下页面底色与白色搜索框接近，靠常显描边 + 二级阴影把输入区域托出来 */
.search-box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-bg-surface);
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-elevation-2);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-5);
  border: 1px solid var(--color-border-hover);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.search-box:hover {
  border-color: var(--color-brand-300);
}

.search-box:focus-within {
  box-shadow: var(--shadow-elevation-3);
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
  /* 搜索框是首屏视觉焦点，高度不低于 48px */
  height: 48px;
  font-size: var(--text-md);
  color: var(--color-text-primary);
}

.search-box input::placeholder {
  color: var(--color-text-tertiary);
}

/* 用 brand-600 而非 brand-500 打底：白字在 brand-500 上对比度只有约 2.3:1，看不清 */
.search-box button {
  /* 比输入框矮一圈，嵌在圆角搜索框内 */
  height: 40px;
  padding: 0 var(--space-6);
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-brand-600);
  box-shadow: var(--shadow-elevation-1);
  /* 品牌色底上的文字在两种主题下都用白色 */
  color: #fff;
  font-size: var(--text-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: background 0.15s ease;
}

.search-box button:hover {
  background: var(--color-brand-700);
}

.search-box button:active {
  background: var(--color-brand-900);
}

.search-box button:disabled {
  background: var(--color-border);
  box-shadow: none;
  color: var(--color-text-tertiary);
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

/* 手机：容器真正吃满屏宽（水平零边距，词典卡片 100%），词条内容区由
   EntryPanel 自己留 8px 内边距（约 95% 可用宽度）。此前保留的 8px 容器边距
   叠加 panel-body 内边距，实测词条内容只占屏宽 87%，仍显窄。
   头部（搜索框/标签行/检索范围行）整体收紧，小屏一屏能多看一两行内容。 */
@media (max-width: 640px) {
  .search-page {
    width: 100%;
    max-width: none;
    padding: var(--space-3) 0;
    gap: var(--space-3);
  }

  .search-head {
    gap: var(--space-2);
  }

  /* 搜索栏高度约 -40%：48px 输入框 + 40px 按钮压到 28/26px */
  .search-box input {
    height: 28px;
    font-size: var(--text-sm);
  }

  .search-box button {
    flex-shrink: 0;
    white-space: nowrap;
    height: 26px;
    padding: 0 var(--space-3);
    font-size: var(--text-xs);
  }

  /* 标签行上下收紧 */
  .scope-tabs {
    gap: var(--space-1);
  }

  .scope-tabs button {
    padding: 2px var(--space-2);
  }

  /* 检索范围开关行上下收紧 */
  .scope {
    gap: var(--space-1);
  }

  .scope-toggle {
    padding: 2px var(--space-2);
  }

  .search-box {
    flex-wrap: nowrap;
  }

  .search-box input {
    flex: 1;
    min-width: 0;
  }

  .search-box button {
    flex-shrink: 0;
    white-space: nowrap;
    padding: 0 var(--space-3);
  }
}
</style>
