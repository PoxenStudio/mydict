<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}

.auth-card {
  width: 100%;
  max-width: 360px;
  background: var(--color-bg-surface);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-elevation-2);
  padding: var(--space-6);
}

h1 {
  margin: 0 0 var(--space-2);
  font-size: var(--text-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.subtitle {
  margin: 0 0 var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}
</style>
