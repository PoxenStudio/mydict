<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'

defineProps<{ loading?: boolean }>()
const emit = defineEmits<{ refresh: [] }>()
</script>

<template>
  <el-button
    class="refresh-btn"
    circle
    text
    title="刷新"
    :icon="Refresh"
    :loading="loading"
    @click="emit('refresh')"
  />
</template>

<style scoped>
.refresh-btn {
  color: var(--color-text-tertiary);
}

.refresh-btn:hover {
  color: var(--color-brand-600);
}
</style>
