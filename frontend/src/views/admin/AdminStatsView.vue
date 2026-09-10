<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as statsApi from '../../api/admin/stats'
import MiniBarChart from '../../components/admin/MiniBarChart.vue'
import type { StatRow, StatsDimension, TopWordRow } from '../../types/stats'

const dimension = ref<StatsDimension>('date')
const startDate = ref('')
const endDate = ref('')
const rows = ref<StatRow[]>([])
const topWords = ref<TopWordRow[]>([])
const loading = ref(false)

const dimensionOptions: { value: StatsDimension; label: string }[] = [
  { value: 'date', label: '按日期' },
  { value: 'token', label: '按 Token' },
  { value: 'user', label: '按用户' },
  { value: 'source', label: '按来源' },
]

async function load() {
  loading.value = true
  try {
    const [statRows, words] = await Promise.all([
      statsApi.getDimensionStats(
        dimension.value,
        startDate.value || undefined,
        endDate.value || undefined,
      ),
      statsApi.getTopWords(startDate.value || undefined, endDate.value || undefined, 10),
    ])
    rows.value = statRows
    topWords.value = words
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(dimension, load)

async function exportCsv() {
  const blob = await statsApi.exportDimensionStatsCsv(
    dimension.value,
    startDate.value || undefined,
    endDate.value || undefined,
  )
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `stats-${dimension.value}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="page">
    <h1>用量统计</h1>

    <div class="toolbar">
      <el-radio-group v-model="dimension">
        <el-radio-button v-for="opt in dimensionOptions" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-model="startDate"
        type="date"
        placeholder="开始日期"
        value-format="YYYY-MM-DD"
        @change="load"
      />
      <el-date-picker
        v-model="endDate"
        type="date"
        placeholder="结束日期"
        value-format="YYYY-MM-DD"
        @change="load"
      />
      <el-button @click="exportCsv">导出 CSV</el-button>
    </div>

    <section v-loading="loading" class="panel">
      <h2>{{ dimensionOptions.find((o) => o.value === dimension)?.label }}查询量</h2>
      <MiniBarChart
        :rows="
          rows.map((r) => ({
            label: r.label,
            value: r.query_count,
            secondary: r.rate_limited_count || undefined,
          }))
        "
      />
    </section>

    <section class="panel">
      <h2>Top 热门查询词</h2>
      <MiniBarChart :rows="topWords.map((w) => ({ label: w.word, value: w.count }))" />
    </section>
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: var(--space-6) auto;
  padding: 0 var(--space-4);
}

h1 {
  font-size: var(--text-xl);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-5);
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.panel {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-5);
  margin-bottom: var(--space-4);
}

.panel h2 {
  font-size: var(--text-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-4);
}
</style>
