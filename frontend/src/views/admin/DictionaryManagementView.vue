<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as dictApi from '../../api/admin/dictionaries'
import DictionaryImportDialog from '../../components/admin/DictionaryImportDialog.vue'
import RefreshButton from '../../components/admin/RefreshButton.vue'
import { LANGUAGE_OPTIONS, langLabel } from '../../utils/language'
import type { DictionaryItem, DictionaryStatus, TestQueryEntry } from '../../types/dictionary'

const dictionaries = ref<DictionaryItem[]>([])
const loading = ref(false)

async function loadDictionaries() {
  loading.value = true
  try {
    dictionaries.value = await dictApi.listDictionaries()
    // 列表重新拉取后旧的勾选可能失效，清空
    selectedIds.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadDictionaries)

// --- 启用/禁用 ---
async function toggleStatus(item: DictionaryItem) {
  const updated =
    item.status === 'enabled'
      ? await dictApi.disableDictionary(item.id)
      : await dictApi.enableDictionary(item.id)
  const index = dictionaries.value.findIndex((d) => d.id === item.id)
  if (index !== -1) dictionaries.value[index] = updated
}

// --- 批量启用/停用 ---
const selectedIds = ref<number[]>([])
const statusBatchRunning = ref(false)

const allSelected = computed(
  () => dictionaries.value.length > 0 && selectedIds.value.length === dictionaries.value.length,
)
const someSelected = computed(
  () => selectedIds.value.length > 0 && selectedIds.value.length < dictionaries.value.length,
)

function toggleSelect(id: number) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

function toggleSelectAll(checked: string | number | boolean) {
  selectedIds.value = checked ? dictionaries.value.map((item) => item.id) : []
}

async function batchSetStatus(status: DictionaryStatus) {
  if (selectedIds.value.length === 0) return
  const ids = [...selectedIds.value]
  statusBatchRunning.value = true
  try {
    const updated = await dictApi.setBatchStatus(ids, status)
    for (const item of updated) {
      const index = dictionaries.value.findIndex((d) => d.id === item.id)
      if (index !== -1) dictionaries.value[index] = item
    }
    selectedIds.value = []
    ElMessage.success(`已${status === 'enabled' ? '启用' : '停用'} ${updated.length} 部词典`)
  } finally {
    statusBatchRunning.value = false
  }
}

// --- 编辑名称/语言方向 ---
const editDialogVisible = ref(false)
const editing = ref(false)
const editTarget = ref<DictionaryItem | null>(null)
const editForm = reactive({ name: '', lang_from: '', lang_to: '' })

function openEdit(item: DictionaryItem) {
  editTarget.value = item
  editForm.name = item.name
  editForm.lang_from = item.lang_from
  editForm.lang_to = item.lang_to
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editTarget.value) return
  if (!editForm.name.trim()) {
    ElMessage.warning('请填写词典名称')
    return
  }
  editing.value = true
  try {
    const updated = await dictApi.updateDictionary(editTarget.value.id, {
      name: editForm.name.trim(),
      lang_from: editForm.lang_from,
      lang_to: editForm.lang_to,
    })
    const index = dictionaries.value.findIndex((d) => d.id === updated.id)
    if (index !== -1) dictionaries.value[index] = updated
    ElMessage.success('已保存')
    editDialogVisible.value = false
  } finally {
    editing.value = false
  }
}

// --- 删除 ---
async function confirmDelete(item: DictionaryItem) {
  const fileHint =
    item.import_method === 'upload'
      ? '同时会删除已上传归档的原始词典文件。'
      : '从服务器目录导入的原始文件不会被删除，仍留在 /data/dicts，如不再需要请自行清理。'
  try {
    await ElMessageBox.confirm(
      `确认删除词典「${item.name}」？此操作不可恢复，词条数据将被清空。${fileHint}`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  // 后端删除本身很快，但历史数据量大时清理磁盘空间的部分是异步的，不等接口返回，
  // 直接从列表里移除，请求失败再把词典恢复显示（具体错误已由响应拦截器统一提示）。
  const snapshot = dictionaries.value
  dictionaries.value = snapshot.filter((d) => d.id !== item.id)
  ElMessage.success('已删除')
  try {
    await dictApi.deleteDictionary(item.id)
  } catch {
    dictionaries.value = snapshot
  }
}

// --- 拖拽排序 ---
const dragIndex = ref<number | null>(null)

function onDragStart(index: number) {
  dragIndex.value = index
}

async function onDrop(targetIndex: number) {
  if (dragIndex.value === null || dragIndex.value === targetIndex) return
  const list = [...dictionaries.value]
  const [moved] = list.splice(dragIndex.value, 1)
  list.splice(targetIndex, 0, moved)
  dictionaries.value = list
  dragIndex.value = null
  dictionaries.value = await dictApi.reorderDictionaries(list.map((d) => d.id))
}

// --- 导入弹窗 ---
const importDialogVisible = ref(false)

// --- 测试查询 ---
const testQueryDialogVisible = ref(false)
const testQueryTarget = ref<DictionaryItem | null>(null)
const testQueryWord = ref('')
const testQueryResults = ref<TestQueryEntry[]>([])

function openTestQuery(item: DictionaryItem) {
  testQueryTarget.value = item
  testQueryWord.value = ''
  testQueryResults.value = []
  testQueryDialogVisible.value = true
}

async function runTestQuery() {
  if (!testQueryTarget.value || !testQueryWord.value.trim()) return
  testQueryResults.value = await dictApi.testQuery(
    testQueryTarget.value.id,
    testQueryWord.value.trim(),
  )
}

// 部分 ECDICT 数据（含已导入的旧数据）把多行释义存成字面 "\n" 而非真换行，
// 这里兜底转换一次，避免预览里直接显示出 \n 这两个字符。
function definitionHtml(definition: string) {
  return definition.replace(/\\n/g, '\n')
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div class="title-row">
        <h1>词典管理</h1>
        <RefreshButton :loading="loading" @refresh="loadDictionaries" />
      </div>
      <el-button type="primary" @click="importDialogVisible = true">导入词典</el-button>
    </div>

    <div v-if="selectedIds.length" class="batch-bar">
      <span class="batch-count">已选 {{ selectedIds.length }} 部</span>
      <el-button size="small" :loading="statusBatchRunning" @click="batchSetStatus('enabled')">
        批量启用
      </el-button>
      <el-button size="small" :loading="statusBatchRunning" @click="batchSetStatus('disabled')">
        批量停用
      </el-button>
      <el-button text size="small" :disabled="statusBatchRunning" @click="selectedIds = []">
        取消选择
      </el-button>
    </div>

    <div v-loading="loading" class="dict-list">
      <div class="dict-list-header">
        <span class="col-select">
          <el-checkbox
            :model-value="allSelected"
            :indeterminate="someSelected"
            aria-label="全选词典"
            @change="toggleSelectAll"
          />
        </span>
        <span class="col-drag"></span>
        <span class="col-name">名称</span>
        <span class="col-format">格式</span>
        <span class="col-lang">语言方向</span>
        <span class="col-count">词条数</span>
        <span class="col-status">状态</span>
        <span class="col-actions">操作</span>
      </div>

      <div
        v-for="(item, index) in dictionaries"
        :key="item.id"
        class="dict-row"
        :class="{ selected: selectedIds.includes(item.id) }"
        draggable="true"
        @dragstart="onDragStart(index)"
        @dragover.prevent
        @drop="onDrop(index)"
      >
        <span class="col-select" @click.stop>
          <el-checkbox
            :model-value="selectedIds.includes(item.id)"
            :aria-label="`选择 ${item.name}`"
            @change="toggleSelect(item.id)"
          />
        </span>
        <span class="col-drag" title="拖拽调整顺序">⠿</span>
        <span class="col-name">{{ item.name }}</span>
        <span class="col-format"
          ><el-tag size="small">{{ item.format }}</el-tag></span
        >
        <span class="col-lang"
          >{{ langLabel(item.lang_from) }} → {{ langLabel(item.lang_to) }}</span
        >
        <span class="col-count">{{ item.word_count }}</span>
        <span class="col-status">
          <el-switch
            :model-value="item.status === 'enabled'"
            :loading="statusBatchRunning"
            @change="toggleStatus(item)"
          />
        </span>
        <span class="col-actions">
          <el-button text @click="openEdit(item)">编辑</el-button>
          <el-button text type="danger" @click="confirmDelete(item)">删除</el-button>
          <el-button text @click="openTestQuery(item)">测试查询</el-button>
        </span>
      </div>

      <div v-if="!loading && dictionaries.length === 0" class="empty-state">
        暂无词典，点击右上角「导入词典」开始导入。
      </div>
    </div>

    <el-dialog v-model="editDialogVisible" title="编辑词典" width="var(--size-dialog-sm)">
      <el-form label-position="top" @submit.prevent="submitEdit">
        <el-form-item label="词典名称">
          <el-input v-model="editForm.name" placeholder="如：牛津高阶英汉双解词典" />
        </el-form-item>
        <div class="lang-row">
          <el-form-item label="源语言">
            <el-select v-model="editForm.lang_from" style="width: 100%">
              <el-option
                v-for="opt in LANGUAGE_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="目标语言">
            <el-select v-model="editForm.lang_to" style="width: 100%">
              <el-option
                v-for="opt in LANGUAGE_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <DictionaryImportDialog v-model="importDialogVisible" @imported="loadDictionaries" />

    <el-dialog
      v-model="testQueryDialogVisible"
      :title="`测试查询 - ${testQueryTarget?.name ?? ''}`"
      width="var(--size-dialog-md)"
    >
      <div class="test-query">
        <el-input v-model="testQueryWord" placeholder="输入词语前缀" @keyup.enter="runTestQuery">
          <template #append>
            <el-button @click="runTestQuery">查询</el-button>
          </template>
        </el-input>
        <div class="test-query-results">
          <div v-for="(entry, i) in testQueryResults" :key="i" class="result-card">
            <div class="result-word">
              {{ entry.word }}
              <span v-if="entry.phonetic" class="result-phonetic">[{{ entry.phonetic }}]</span>
            </div>
            <div class="result-definition" v-html="definitionHtml(entry.definition)"></div>
          </div>
          <p v-if="testQueryWord && testQueryResults.length === 0" class="hint">未查询到结果</p>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  max-width: var(--size-content-md);
  margin: var(--space-6) auto;
  padding: 0 var(--space-4);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-5);
}

.page-header h1 {
  font-size: var(--text-xl);
  color: var(--color-text-primary);
  margin: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.dict-list {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  overflow: hidden;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-surface);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-elevation-1);
  font-size: var(--text-sm);
}

.batch-count {
  margin-right: var(--space-2);
  color: var(--color-text-secondary);
}

.dict-list-header,
.dict-row {
  display: grid;
  grid-template-columns:
    var(--size-control-md) var(--size-control-md)
    2fr 1fr 1fr 0.8fr 0.8fr 1.4fr;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}

.dict-list-header {
  background: var(--color-bg-base);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
}

.dict-row {
  border-top: 1px solid var(--color-border);
  cursor: grab;
}

.dict-row:hover {
  background: var(--color-hover-tint);
}

.dict-row.selected {
  background: var(--color-hover-tint);
}

.col-select {
  display: flex;
  align-items: center;
  cursor: default;
}

.col-drag {
  color: var(--color-text-tertiary);
  text-align: center;
}

.col-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-start;
  gap: var(--space-2);
}

.col-actions .el-button + .el-button {
  margin-left: 0;
}

.empty-state {
  padding: var(--space-7);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.path-icon.disabled {
  color: var(--color-text-tertiary);
  cursor: default;
  pointer-events: none;
}

.hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.test-query-results {
  margin-top: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-height: var(--size-scroll-md);
  overflow-y: auto;
}

.result-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}

.result-word {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.result-phonetic {
  margin-left: var(--space-2);
  font-weight: var(--font-weight-regular);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.result-definition {
  margin-top: var(--space-1);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  white-space: pre-wrap;
}
</style>
