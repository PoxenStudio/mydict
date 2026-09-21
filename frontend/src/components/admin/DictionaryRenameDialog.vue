<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { renameDictionaries } from '../../api/admin/dictionaries'
import type { RenamePreviewItem } from '../../types/dictionary'

const props = defineProps<{
  modelValue: boolean
  /** 列表里勾选的词典；为空时「仅选中的」不可用，只能对全部词典操作 */
  selectedIds: number[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** 已经真正改名落库，父级据此刷新列表 */
  renamed: []
}>()

const pattern = ref('')
const replacement = ref('')
const scope = ref<'all' | 'selected'>('all')
const previewing = ref(false)
const applying = ref(false)
const preview = ref<RenamePreviewItem[] | null>(null)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const canUseSelected = computed(() => props.selectedIds.length > 0)

// 输入一改就把上一次的预览作废，免得照着过期结果点「应用」
watch([pattern, replacement, scope], () => {
  preview.value = null
})

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    preview.value = null
    if (!canUseSelected.value) scope.value = 'all'
  },
)

function targetIds(): number[] | undefined {
  return scope.value === 'selected' && canUseSelected.value ? props.selectedIds : undefined
}

async function runPreview() {
  previewing.value = true
  try {
    const resp = await renameDictionaries({
      pattern: pattern.value,
      replacement: replacement.value,
      dictionary_ids: targetIds(),
      dry_run: true,
    })
    preview.value = resp.items
    if (!resp.items.length) ElMessage.info('没有词典名匹配这个正则')
  } finally {
    previewing.value = false
  }
}

async function apply() {
  applying.value = true
  try {
    const resp = await renameDictionaries({
      pattern: pattern.value,
      replacement: replacement.value,
      dictionary_ids: targetIds(),
      dry_run: false,
    })
    ElMessage.success(`已重命名 ${resp.items.length} 部词典`)
    emit('renamed')
    visible.value = false
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="批量重命名" width="var(--size-dialog-md)">
    <el-form label-width="72px" @submit.prevent>
      <el-form-item label="作用范围">
        <el-radio-group v-model="scope">
          <el-radio value="all">全部词典</el-radio>
          <el-radio value="selected" :disabled="!canUseSelected">
            仅选中的 {{ selectedIds.length }} 部
          </el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="查找">
        <el-input v-model="pattern" placeholder="正则表达式，例如 ^\[中\]\s*" clearable />
      </el-form-item>
      <el-form-item label="替换为">
        <el-input v-model="replacement" placeholder="留空表示删掉匹配到的部分" clearable />
      </el-form-item>
    </el-form>

    <p class="rename-hint">
      用 Python 正则语法；替换串里 <code>\1</code> 引用第一个捕获组。先「预览」核对改名结果，确认无误再「应用」。
    </p>

    <el-table v-if="preview" :data="preview" size="small" max-height="300">
      <el-table-column prop="name" label="原名称" show-overflow-tooltip />
      <el-table-column prop="new_name" label="新名称" show-overflow-tooltip />
    </el-table>

    <template #footer>
      <el-button :loading="previewing" @click="runPreview">预览</el-button>
      <el-button type="primary" :loading="applying" :disabled="!preview?.length" @click="apply">
        应用
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.rename-hint {
  margin: 0;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  line-height: var(--leading-body);
}

.rename-hint code {
  font-family: var(--font-family-mono);
  color: var(--color-text-secondary);
}
</style>
