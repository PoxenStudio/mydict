<script setup lang="ts">
defineProps<{
  favorited: boolean
  loading?: boolean
}>()

const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <button
    type="button"
    class="favorite-btn"
    :class="{ favorited }"
    :disabled="loading"
    :aria-label="favorited ? '取消收藏' : '加入生词本'"
    @click="emit('toggle')"
  >
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      :fill="favorited ? 'currentColor' : 'none'"
      stroke="currentColor"
      stroke-width="1.5"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M12 3.5l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3.5Z"
      />
    </svg>
  </button>
</template>

<style scoped>
.favorite-btn {
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-secondary);
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 100ms ease;
}

.favorite-btn:hover {
  background: var(--color-hover-tint);
}

.favorite-btn.favorited {
  color: var(--color-brand-500);
  border-color: var(--color-brand-500);
  transform: scale(1.08);
}
</style>
