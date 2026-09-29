<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import NavBar from '../components/NavBar.vue'
import EntryFrame from '../components/EntryFrame.vue'
import SkeletonList from '../components/SkeletonList.vue'
import EmptyState from '../components/EmptyState.vue'
import { deleteVocab, listVocab, listVocabLanguages } from '../api/vocab'
import { getVocabEntryHtml } from '../api/dict'
import { langLabel } from '../utils/language'
import type { VocabItem } from '../types/vocab'

const router = useRouter()
const items = ref<VocabItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const search = ref('')
const loading = ref(true)

// 生词本里出现过的来源语言，用于左上角的分类 tab；只有一种语言时不必展示切换。
const languages = ref<string[]>([])
// 空字符串代表「全部」
const activeLang = ref('')

async function load() {
  loading.value = true
  try {
    const resp = await listVocab(search.value, page.value, pageSize, activeLang.value || undefined)
    items.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
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

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})

watch(page, load)

// 词条默认折叠：一页 20 条各带一个沙箱 iframe，全部展开一次就要取 20 份词条文档。
// 所以展开过才挂载（mountedIds），首次点击前连请求都不发——和查询页 EntryPanel 同一套做法。
const expandedIds = ref<Set<number>>(new Set())
const mountedIds = ref<Set<number>>(new Set())

function isExpanded(id: number) {
  return expandedIds.value.has(id)
}

function isMounted(id: number) {
  return mountedIds.value.has(id)
}

/** 没有释义也没有备注就没有可展开的内容，不显示箭头、点击也不响应 */
function hasBody(item: VocabItem) {
  return Boolean(item.definition || item.note)
}

function toggle(item: VocabItem) {
  if (!hasBody(item)) return
  const expanded = new Set(expandedIds.value)
  const mounted = new Set(mountedIds.value)
  if (expanded.has(item.id)) {
    expanded.delete(item.id)
  } else {
    expanded.add(item.id)
    mounted.add(item.id)
  }
  expandedIds.value = expanded
  mountedIds.value = mounted
}

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
        <h1>我的生词本</h1>
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
        <div v-for="item in items" :key="item.id" class="vocab-item">
          <div class="vocab-main">
            <div
              class="word-row"
              :class="{ clickable: hasBody(item) }"
              role="button"
              :tabindex="hasBody(item) ? 0 : -1"
              :aria-expanded="hasBody(item) ? isExpanded(item.id) : undefined"
              @click="toggle(item)"
              @keydown.enter.prevent="toggle(item)"
              @keydown.space.prevent="toggle(item)"
            >
              <span
                v-if="hasBody(item)"
                class="chevron"
                :class="{ open: isExpanded(item.id) }"
                aria-hidden="true"
                >›</span
              >
              <span class="word">{{ item.word }}</span>
              <span v-if="item.phonetic" class="phonetic">[{{ item.phonetic }}]</span>
              <!-- 词条级生词本：同一个词可能来自不同词典，标出来源 -->
              <span v-if="item.dictionary_name" class="dict-name">{{ item.dictionary_name }}</span>
            </div>
            <!--
              折叠不用 display:none：隐藏的 iframe 会按 0 宽度排版、上报一个极大的高度，把
              EntryFrame 的增长守卫误触发成「冻结可滚动」。收成高度 0 后 iframe 仍按真实宽度
              排版，inert 挡住键盘焦点落进看不见的内容。默认折叠，展开过才挂载。
            -->
            <div
              v-if="hasBody(item) && (isExpanded(item.id) || isMounted(item.id))"
              class="vocab-body"
              :class="{ collapsed: !isExpanded(item.id) }"
              :inert="!isExpanded(item.id)"
            >
              <!--
                释义用隔离 iframe 渲染：词典自带的 <style>/内联事件在应用源下会污染整个
                界面、并让第三方词典脚本够到 localStorage 里的 token。
                这里取的是**收藏当时的释义快照**（/vocab/{id}/entry），不是按词典实时取，
                所以词典后来被删或改都不影响生词本。
              -->
              <EntryFrame
                v-if="item.definition"
                :key="item.id"
                class="definition"
                :loader="() => getVocabEntryHtml(item.id)"
              />
              <p v-if="item.note" class="note">备注：{{ item.note }}</p>
            </div>
          </div>
          <button type="button" class="remove-btn" aria-label="删除生词" @click="remove(item)">
            删除
          </button>
        </div>
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
  justify-content: space-between;
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

.vocab-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  /* 竖向内边距 × 0.6：16px → 9.6px（--space-4 是 16px）。
     和行高、行间距一样统一按 0.6 缩放，相邻两条标题行之间的距离才是干净的 -40% */
  padding: calc(var(--space-4) * 0.6) var(--space-4);
}

/*
 * flex: 1 是「释义只占一半宽度」的修复点：.vocab-item 是 flex 行，.vocab-main 默认
 * flex-grow:0，宽度按内容撑——而里面两个孩子都是 width:100%（百分比在固有尺寸里退化成
 * auto），iframe 就按替换元素默认的 300px 参与计算，于是只剩固定的一小条，右边留给
 * 「删除」一大片空白。min-width:0 允许它被压到 0，否则内容的最小尺寸会顶住不让收缩。
 */
.vocab-main {
  flex: 1;
  min-width: 0;
}

.word-row {
  /*
   * 标题行行高减少 40%：全局 --leading-body 是 1.6，1.6 × 0.6 = 0.96。
   * 用无单位数值让子元素各自按自己的字号算行盒，所以字号（--text-lg 18px）没变，
   * 只有行盒被压扁（18 × 0.96 = 17.28px）。
   *
   * 做成自定义属性是为了让箭头也吃到同一个比例——写 line-height:inherit 只会继承
   * 父级的**计算值**（14 × 0.96 = 13.44px），箭头按自己的 18px 字号就少了一截。
   */
  --vocab-title-leading: 0.96;
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  line-height: var(--vocab-title-leading);
  /* 三列布局下标题行要能被压缩，否则内容的最小尺寸会顶破卡片 */
  min-width: 0;
}

.word-row.clickable {
  cursor: pointer;
  user-select: none;
}

.chevron {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
  font-size: var(--text-lg);
  /* 跟随标题行的比例，否则这个 18px 的字形会把行盒顶回 18px，40% 的压缩只兑现一半 */
  line-height: var(--vocab-title-leading);
  transition: transform 0.15s ease;
}

.chevron.open {
  transform: rotate(90deg);
}

.word {
  font-size: var(--text-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  /* 三列之后单卡变窄，长词头宁可省略号也不要顶破卡片（字号不变） */
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dict-name {
  /* 词典名可能很长（「牛津高阶英汉双解词典第10版」）：封顶 45% 并打省略号，
     免得它把左边的词头挤没（同查询页 EntryPanel 的处理） */
  flex-shrink: 0;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 0 4px;
  margin-left: 6px;
}

.phonetic {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.vocab-body {
  margin-top: var(--space-2);
}

/* 与查询页 EntryPanel 的折叠一致：收高度而不是 display:none，保住 iframe 的真实宽度 */
.vocab-body.collapsed {
  height: 0;
  margin-top: 0;
  overflow: hidden;
  visibility: hidden;
}

.definition {
  display: block;
}

.note {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.remove-btn {
  flex-shrink: 0;
  border: none;
  background: none;
  color: var(--color-danger);
  cursor: pointer;
  font-size: var(--text-sm);
  /* 折叠态卡片的实际高度曾被这个按钮决定（13px × 全局 1.6 = 20.8px，比标题行的
     17.52px 还高），于是标题行压了 40% 卡片却压不动。压到 1 之后卡片高度回到标题行
     说了算，相邻两行标题之间的距离才真正接近 -40% */
  line-height: 1;
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
