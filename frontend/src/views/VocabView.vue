<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import NavBar from '../components/NavBar.vue'
import VocabCompactCard from '../components/VocabCompactCard.vue'
import SkeletonList from '../components/SkeletonList.vue'
import EmptyState from '../components/EmptyState.vue'
import { deleteVocab, listVocab, listVocabLanguages } from '../api/vocab'
import { langLabel } from '../utils/language'
import type { SortOrder, VocabItem, VocabSort } from '../types/vocab'

const router = useRouter()
const items = ref<VocabItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const search = ref('')
const loading = ref(true)
const sort = ref<VocabSort>('date')
const order = ref<SortOrder>('desc')

const sortOptions: { key: VocabSort; label: string; defaultOrder: SortOrder }[] = [
  { key: 'word', label: '按名称排序', defaultOrder: 'asc' },
  { key: 'date', label: '按日期排序', defaultOrder: 'desc' },
]

// 生词本里出现过的来源语言，用于左上角的分类 tab；只有一种语言时不必展示切换。
const languages = ref<string[]>([])
// 空字符串代表「全部」
const activeLang = ref('')

// 只有首屏（还没有数据）才显示骨架屏；排序/翻页/筛选时保留旧列表直到新数据到达，避免闪烁
let loadSeq = 0

async function load() {
  const seq = ++loadSeq
  try {
    const resp = await listVocab(
      search.value,
      page.value,
      pageSize,
      activeLang.value || undefined,
      sort.value,
      order.value,
    )
    // 连续点击时只采用最后一次请求的结果
    if (seq !== loadSeq) return
    items.value = resp.items
    total.value = resp.total
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function loadLanguages() {
  try {
    languages.value = await listVocabLanguages()
  } catch {
    // 分类加载失败不影响生词本本身，只是不显示 tab
  }
}

onMounted(() => {
  load()
  loadLanguages()
})

function selectLang(lang: string) {
  if (activeLang.value === lang) return
  activeLang.value = lang
  page.value = 1
  load()
}

function selectSort(key: VocabSort, defaultOrder: SortOrder) {
  if (sort.value === key) {
    order.value = order.value === 'asc' ? 'desc' : 'asc'
  } else {
    sort.value = key
    order.value = defaultOrder
  }
  if (page.value === 1) load()
  else page.value = 1
}

function sortTitle(opt: { key: VocabSort; label: string }) {
  if (sort.value !== opt.key) return opt.label
  return `${opt.label}（${order.value === 'asc' ? '升序' : '降序'}）`
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})

watch(page, load)

async function remove(item: VocabItem) {
  try {
    await ElMessageBox.confirm(`确认从生词本移除「${item.word}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
    })
  } catch {
    return
  }
  await deleteVocab(item.id)
  ElMessage.success('已删除')
  load()
  loadLanguages()
}
</script>

<template>
  <div class="page">
    <NavBar />
    <main class="vocab-page">
      <div class="header">
        <div class="title-group">
          <h1>我的生词本</h1>
          <button
            v-for="opt in sortOptions"
            :key="opt.key"
            type="button"
            class="sort-btn"
            :class="{ active: sort === opt.key }"
            :title="sortTitle(opt)"
            :aria-label="sortTitle(opt)"
            :aria-pressed="sort === opt.key"
            @click="selectSort(opt.key, opt.defaultOrder)"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <text v-if="opt.key === 'word'" x="1" y="11" class="sort-glyph">A</text>
              <text v-if="opt.key === 'word'" x="1" y="22" class="sort-glyph">Z</text>
              <g v-else class="sort-calendar">
                <rect x="2" y="5" width="12" height="13" rx="2" />
                <path d="M2 9.5h12M5.5 3v4M10.5 3v4" />
              </g>
              <path
                class="sort-arrow"
                :d="
                  sort === opt.key && order === 'asc'
                    ? 'M19 21V4m-3.5 3.5L19 4l3.5 3.5'
                    : 'M19 3v17m-3.5-3.5L19 20l3.5-3.5'
                "
              />
            </svg>
          </button>
        </div>
        <el-input v-model="search" placeholder="搜索生词" clearable style="width: 220px" />
      </div>

      <div v-if="languages.length > 1" class="lang-tabs">
        <button
          type="button"
          class="lang-tab"
          :class="{ active: activeLang === '' }"
          @click="selectLang('')"
        >
          全部
        </button>
        <button
          v-for="lang in languages"
          :key="lang"
          type="button"
          class="lang-tab"
          :class="{ active: activeLang === lang }"
          @click="selectLang(lang)"
        >
          {{ langLabel(lang) }}
        </button>
      </div>

      <SkeletonList v-if="loading" :rows="4" />

      <EmptyState
        v-else-if="items.length === 0"
        :title="
          activeLang
            ? `「${langLabel(activeLang)}」下还没有生词`
            : '生词本还是空的，去查询页收藏第一个生词吧'
        "
        action-text="去查询"
        @action="router.push('/')"
      />

      <div v-else class="vocab-list">
        <VocabCompactCard v-for="item in items" :key="item.id" :item="item" @remove="remove" />
      </div>

      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        class="pagination"
      />
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg-base);
}

.vocab-page {
  /* 720px 是单列正文的宽度，放不下三列词条卡片；改用大内容宽度 token（1220px） */
  max-width: var(--size-content-lg);
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}

.header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

/* 平面 tab 切换：无圆角、靠底边框区分选中态，浅色/深色主题都只吃 Token，颜色自动跟随 */
.lang-tabs {
  display: flex;
  margin-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.lang-tab {
  border: none;
  border-radius: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  margin-bottom: -1px;
}

.lang-tab:hover {
  color: var(--color-text-primary);
}

.lang-tab.active {
  color: var(--color-brand-600);
  border-bottom-color: var(--color-brand-500);
  font-weight: var(--font-weight-medium);
}

.title-group {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.sort-btn {
  display: inline-flex;
  padding: var(--space-1);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
}

.sort-btn:hover {
  background: var(--color-hover-tint);
  color: var(--color-text-primary);
}

.sort-btn.active {
  color: var(--color-brand-600);
}

.sort-btn svg {
  /* 图标尺寸一次性值：标题旁的小工具图标，按需求固定 18×18 */
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.sort-glyph {
  fill: currentColor;
  stroke: none;
  font-size: var(--text-xs);
  font-weight: var(--font-weight-bold);
}

.header h1 {
  font-size: var(--text-xl);
  color: var(--color-text-primary);
  margin: 0;
}

/*
 * PC 上同行三列；平板断点（1023px）以下两列、手机（640px）一列，见文件末尾的媒体查询。
 *
 * align-items:start 而不是默认的 stretch：卡片高度由自身内容决定。生词本里展开一条
 * 词条可能是几千像素高（千篇那条实体词条 4986px），stretch 会把同一排另外两张卡也拉成
 * 同样高，整屏只剩空白。
 */
.vocab-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: start;
  /* 行间距 × 0.6：12px → 7.2px（--space-3 是 12px） */
  row-gap: calc(var(--space-3) * 0.6);
  column-gap: var(--space-3);
}

.pagination {
  margin-top: var(--space-5);
  justify-content: center;
}

/* 列数随视口退让；断点沿用全站既有写法（平板 1023px / 手机 640px）。
   两列、一列时行间距同样保持减少后的 7px，只有列间距跟着列数走。 */
@media (max-width: 1023px) {
  .vocab-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .vocab-list {
    grid-template-columns: minmax(0, 1fr);
  }

  .vocab-page {
    padding: var(--space-4);
  }
}
</style>
