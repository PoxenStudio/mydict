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
            <div class="word-row">
              <span class="word">{{ item.word }}</span>
              <span v-if="item.phonetic" class="phonetic">[{{ item.phonetic }}]</span>
            </div>
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
  max-width: 720px;
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

.vocab-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.vocab-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-4);
}

.word-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}

.word {
  font-size: var(--text-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.phonetic {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.definition {
  display: block;
  margin-top: var(--space-2);
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
}

.pagination {
  margin-top: var(--space-5);
  justify-content: center;
}
</style>
