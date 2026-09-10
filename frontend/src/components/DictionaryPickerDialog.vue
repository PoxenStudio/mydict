<script setup lang="ts">
import { ref, watch } from 'vue'
import type { PublicDictionary } from '../types/query'

const props = defineProps<{
  dictionaries: PublicDictionary[]
  currentIds: number[] | null
}>()

const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ confirm: [ids: number[] | null] }>()

const useAll = ref(true)
const selected = ref<number[]>([])

watch(visible, (v) => {
  if (!v) return
  useAll.value = props.currentIds === null
  selected.value = props.currentIds ? [...props.currentIds] : []
})

function submit() {
  emit('confirm', useAll.value ? null : selected.value)
  visible.value = false
}
</script>

<template>
  <el-dialog v-model="visible" title="选择可用词典" width="420px">
    <el-radio-group v-model="useAll" class="mode-group">
      <el-radio :value="true">使用全部已启用词典</el-radio>
      <el-radio :value="false">自定义选择</el-radio>
    </el-radio-group>
    <el-checkbox-group v-if="!useAll" v-model="selected" class="dict-options">
      <el-checkbox v-for="d in dictionaries" :key="d.id" :value="d.id" :label="d.id">
        {{ d.name }}
      </el-checkbox>
    </el-checkbox-group>
    <p v-if="!useAll && dictionaries.length === 0" class="hint">暂无已启用的词典。</p>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.mode-group {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  width: 100%;
  margin-bottom: var(--space-3);
}

.dict-options {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border);
}

.hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}
</style>
