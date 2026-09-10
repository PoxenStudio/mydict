<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import NavBar from '../components/NavBar.vue'
import SkeletonList from '../components/SkeletonList.vue'
import EmptyState from '../components/EmptyState.vue'
import { deleteVocab, listVocab } from '../api/vocab'
import type { VocabItem } from '../types/vocab'

const router = useRouter()
const items = ref<VocabItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const search = ref('')
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const resp = await listVocab(search.value, page.value, pageSize)
    items.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
  }
}

onMounted(load)

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

      <SkeletonList v-if="loading" :rows="4" />

      <EmptyState
        v-else-if="items.length === 0"
        title="生词本还是空的，去查询页收藏第一个生词吧"
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
            <div class="definition" v-html="item.definition"></div>
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
  margin-top: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: var(--leading-body);
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
