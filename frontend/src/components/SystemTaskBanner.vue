<script setup lang="ts">
import { ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { useSystemStatusStore } from '../stores/systemStatus'

const store = useSystemStatusStore()
const dismissed = ref(false)
</script>

<template>
  <div v-if="store.busyNotice && !dismissed" class="banner-wrap">
    <div class="banner" role="status">
      <el-icon class="icon"><InfoFilled /></el-icon>
      <span class="text">{{ store.busyNotice }}</span>
      <button type="button" class="close" aria-label="关闭提示" @click="dismissed = true">×</button>
    </div>
  </div>
</template>

<style scoped>
.banner-wrap {
  padding: var(--space-4) var(--space-4) 0;
}

/* 与首页 .search-page 的内容区同宽（1180px 减去两侧 space-4 内边距） */
.banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  max-width: calc(1180px - 2 * var(--space-4));
  margin: 0 auto;
  padding: var(--space-2) var(--space-4);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-elevation-1);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.icon {
  flex-shrink: 0;
  color: var(--color-info);
}

.text {
  flex: 1;
  min-width: 0;
}

.close {
  border: none;
  background: none;
  cursor: pointer;
  font-size: var(--text-md);
  line-height: 1;
  color: var(--color-text-tertiary);
}

.close:hover {
  color: var(--color-text-primary);
}
</style>
