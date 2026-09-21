<script setup lang="ts">
import { watch } from 'vue'
import { RouterView } from 'vue-router'
import ScrollButtons from './components/ScrollButtons.vue'
import { useSettingsStore } from './stores/settings'

const settingsStore = useSettingsStore()

watch(
  () => settingsStore.siteName,
  (siteName) => {
    document.title = siteName
  },
  { immediate: true },
)
</script>

<template>
  <RouterView />
  <ScrollButtons />
</template>
