<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  rows: { label: string; value: number; secondary?: number }[]
}>()

const max = computed(() => Math.max(1, ...props.rows.map((r) => r.value)))
</script>

<template>
  <div class="bar-chart">
    <div v-for="row in rows" :key="row.label" class="bar-row">
      <span class="bar-label" :title="row.label">{{ row.label }}</span>
      <div class="bar-track">
        <div class="bar-fill" :style="{ width: `${(row.value / max) * 100}%` }" />
      </div>
      <span class="bar-value">
        {{ row.value
        }}<span v-if="row.secondary" class="bar-secondary"> · 限流 {{ row.secondary }}</span>
      </span>
    </div>
    <p v-if="rows.length === 0" class="bar-empty">暂无数据</p>
  </div>
</template>

<style scoped>
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.bar-row {
  display: grid;
  grid-template-columns: 120px 1fr 100px;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
}

.bar-label {
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track {
  height: 10px;
  background: var(--color-bg-base);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: var(--color-brand-500);
  border-radius: var(--radius-full);
  transition: width 200ms ease;
}

.bar-value {
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.bar-secondary {
  color: var(--color-warning);
}

.bar-empty {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
  text-align: center;
  padding: var(--space-4);
  margin: 0;
}
</style>
