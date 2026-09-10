<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    actionText?: string
  }>(),
  { actionText: '' },
)

defineEmits<{ action: [] }>()
</script>

<template>
  <div class="empty-state">
    <svg
      viewBox="0 0 24 24"
      width="48"
      height="48"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
    >
      <circle cx="11" cy="11" r="7" />
      <path stroke-linecap="round" d="M21 21l-4.3-4.3" />
    </svg>
    <p>{{ title }}</p>
    <button v-if="actionText" type="button" class="action-btn" @click="$emit('action')">
      {{ actionText }}
    </button>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8) var(--space-4);
  color: var(--color-text-tertiary);
  text-align: center;
}

.empty-state p {
  margin: 0;
  font-size: var(--text-sm);
}

.action-btn {
  border: 1px solid var(--color-border);
  background: var(--color-bg-surface);
  color: var(--color-brand-600);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  cursor: pointer;
}

.action-btn:hover {
  background: var(--color-brand-50);
  border-color: var(--color-border-hover);
}
</style>
