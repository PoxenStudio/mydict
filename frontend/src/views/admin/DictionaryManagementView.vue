<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, Folder, HomeFilled } from '@element-plus/icons-vue'
import * as dictApi from '../../api/admin/dictionaries'
import * as tasksApi from '../../api/admin/tasks'
import RefreshButton from '../../components/admin/RefreshButton.vue'
import { LANGUAGE_OPTIONS, langLabel } from '../../utils/language'
import type { BackgroundTask } from '../../types/backgroundTask'
import type {
  DictionaryFormat,
  DictionaryItem,
  DictionaryStatus,
  DictsDirFile,
  DictsDirGroup,
  DictsDirListing,
  TestQueryEntry,
} from '../../types/dictionary'

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
type GroupImportStatus = 'pending' | 'imported' | 'importing' | 'success' | 'error' | 'blocked'

const importDialogVisible = ref(false)
const importMode = ref<'upload' | 'dicts-dir'>('upload')
const importing = ref(false)
const importForm = reactive({
  name: '',
  format: 'ecdict' as DictionaryFormat,
  lang_from: 'en',
  lang_to: 'zh-Hans',
})
const uploadFileList = ref<File[]>([])
// ECDICT 一个 CSV 就是一部词典，后端拒绝多选，界面直接限制为单选
const isSingleFileFormat = computed(() => importForm.format === 'ecdict')

// 服务端把目录文件按 (格式, 主干) 归组成词典单元，名称与格式自动给出，语言方向导入时自动识别
const dictsDirPath = ref('')
// 默认只扫当前层；勾上后连子目录一起扫
const dictsDirRecursive = ref(false)
// 只导入释义、不解包 .mdd（省磁盘，代价是没有发音和插图）
const skipResources = ref(false)
const dictsDirDirectories = ref<DictsDirFile[]>([])
const dictsDirDictionaries = ref<DictsDirGroup[]>([])
const dictsDirSkipped = ref<string[]>([])
const selectedGroupKeys = ref<string[]>([])
const groupNames = reactive<Record<string, string>>({})
const groupStatus = reactive<Record<string, GroupImportStatus>>({})
const groupError = reactive<Record<string, string>>({})
const groupLangs = reactive<Record<string, string>>({})
const groupWordCounts = reactive<Record<string, number>>({})
const batchRunning = ref(false)
// 点「停止导入剩余」后置位：在途那部跑完，不再调度后面的
const batchCancelled = ref(false)
const batchSummary = ref('')

const FORMAT_LABELS: Record<DictionaryFormat, string> = {
  mdict: 'MDict',
  stardict: 'StarDict',
  ecdict: 'ECDICT',
}

// 切换格式后旧的文件选择不再适用，清空
watch(
  () => importForm.format,
  () => {
    if (importMode.value !== 'upload') return
    uploadFileList.value = []
  },
)

function openImportDialog() {
  importForm.name = ''
  importForm.format = 'ecdict'
  importForm.lang_from = 'en'
  importForm.lang_to = 'zh-Hans'
  uploadFileList.value = []
  importMode.value = 'upload'
  batchSummary.value = ''
  importDialogVisible.value = true
}

const scanning = ref(false)
// 快速连续触发扫描时只采用最后一次请求的结果
let scanSeq = 0

// 失败时保留当前列表，返回 false（错误已由响应拦截器提示）
async function loadDictsDirScan(path: string): Promise<boolean> {
  const seq = ++scanSeq
  scanning.value = true
  try {
    const listing = await dictApi.listDictsDirFiles(path, dictsDirRecursive.value)
    if (seq !== scanSeq) return true
    applyDictsDirListing(listing)
    return true
  } catch {
    return false
  } finally {
    if (seq === scanSeq) scanning.value = false
  }
}

function applyDictsDirListing(listing: DictsDirListing) {
  dictsDirPath.value = listing.path
  // 递归时列表已覆盖整棵子树，目录行只在非递归下用于下钻
  dictsDirDirectories.value = listing.entries.filter((entry) => entry.is_dir)
  dictsDirDictionaries.value = listing.dictionaries
  dictsDirSkipped.value = listing.skipped
  batchSummary.value = ''
  for (const group of listing.dictionaries) {
    groupNames[group.key] = group.name
    // 以重新扫描的结果为准
    groupStatus[group.key] = group.imported ? 'imported' : group.importable ? 'pending' : 'blocked'
    delete groupError[group.key]
    delete groupLangs[group.key]
    delete groupWordCounts[group.key]
  }
  // 缺件和已导入的默认不勾选；已导入的仍可手动勾上重新导入成另一部词典
  selectedGroupKeys.value = listing.dictionaries
    .filter((group) => group.importable && !group.imported)
    .map((group) => group.key)
}

async function toggleRecursive() {
  if (!(await loadDictsDirScan(dictsDirPath.value))) {
    dictsDirRecursive.value = !dictsDirRecursive.value
  }
}

function openDictsDirEntry(entry: DictsDirFile) {
  if (!entry.is_dir) return
  loadDictsDirScan(dictsDirPath.value ? `${dictsDirPath.value}/${entry.name}` : entry.name)
}

function goToDictsDirRoot() {
  if (dictsDirPath.value) loadDictsDirScan('')
}

function goToDictsDirParent() {
  if (!dictsDirPath.value) return
  const parts = dictsDirPath.value.split('/')
  parts.pop()
  loadDictsDirScan(parts.join('/'))
}

function handleTabChange(name: string | number) {
  if (name === 'dicts-dir') {
    importMode.value = 'dicts-dir'
    loadDictsDirScan('')
  } else {
    importMode.value = 'upload'
  }
}

function handleFileChange(uploadFile: { raw?: File }) {
  if (!uploadFile.raw) return
  if (isSingleFileFormat.value) {
    uploadFileList.value = [uploadFile.raw]
    return
  }
  uploadFileList.value.push(uploadFile.raw)
}

function removeUploadFile(index: number) {
  uploadFileList.value.splice(index, 1)
}

function toggleAllGroups(checked: string | number | boolean) {
  selectedGroupKeys.value = checked
    ? dictsDirDictionaries.value.filter((group) => group.importable).map((group) => group.key)
    : []
}

const allGroupsSelected = computed(() => {
  const keys = dictsDirDictionaries.value.filter((group) => group.importable)
  return keys.length > 0 && keys.every((group) => selectedGroupKeys.value.includes(group.key))
})

const someGroupsSelected = computed(
  () => selectedGroupKeys.value.length > 0 && !allGroupsSelected.value,
)

// 勾选时展示总量，避免一次全选把磁盘写满
const selectedTotalSize = computed(() =>
  dictsDirDictionaries.value
    .filter((group) => selectedGroupKeys.value.includes(group.key))
    .reduce((sum, group) => sum + group.total_size, 0),
)

// 本次已成功导入的源文件，仅用于提示，程序不会删除任何文件
const importedSources = computed(() => {
  const done = dictsDirDictionaries.value.filter((group) => groupStatus[group.key] === 'success')
  return {
    files: done.flatMap((group) => group.files.map((file) => file.relpath)),
    size: done.reduce((sum, group) => sum + group.total_size, 0),
  }
})

function groupStatusLabel(group: DictsDirGroup) {
  switch (groupStatus[group.key]) {
    case 'blocked':
      return group.reason ?? '文件不完整'
    case 'imported':
      return '已导入'
    case 'importing':
      return '导入中…'
    case 'success':
      return '成功'
    case 'error':
      return groupError[group.key] ?? '失败'
    default:
      return '待导入'
  }
}

function groupStatusTagType(group: DictsDirGroup) {
  switch (groupStatus[group.key]) {
    case 'success':
      return 'success'
    case 'error':
      return 'danger'
    case 'importing':
    case 'blocked':
      return 'warning'
    default:
      return 'info'
  }
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms))
}

// 导入接口立即返回 task_id，解析入库在后端线程跑，这里轮询任务状态直到成功/失败
const POLL_INTERVAL_MS = 1000
const POLL_TIMEOUT_MS = 60 * 60 * 1000
const POLL_MAX_CONSECUTIVE_FAILURES = 3

class PollAbortedError extends Error {}

let unmounted = false
onBeforeUnmount(() => {
  unmounted = true
})

async function waitForImportTask(taskId: number) {
  const deadline = Date.now() + POLL_TIMEOUT_MS
  let failures = 0
  while (!unmounted) {
    try {
      const task = await tasksApi.getTask(taskId)
      failures = 0
      if (task.status === 'success') return task
      if (task.status === 'error') throw new Error(task.error ?? '导入失败')
    } catch (err) {
      // 任务自身失败直接抛出；偶发的轮询请求失败容忍几次，任务在后端仍在跑
      if (!(err as { isAxiosError?: boolean } | null)?.isAxiosError) throw err
      failures += 1
      if (failures >= POLL_MAX_CONSECUTIVE_FAILURES) throw err
    }
    if (Date.now() > deadline) throw new Error('等待导入超时，请稍后在词典列表确认是否已完成')
    await sleep(POLL_INTERVAL_MS)
  }
  throw new PollAbortedError()
}

// result 是 Record<string, unknown>，逐字段收窄
function resultNumber(task: BackgroundTask, key: string): number | null {
  const value = task.result?.[key]
  return typeof value === 'number' ? value : null
}

function resultString(task: BackgroundTask, key: string): string | null {
  const value = task.result?.[key]
  return typeof value === 'string' ? value : null
}

function errorMessage(err: unknown): string {
  const serverMessage = (err as { response?: { data?: { message?: string } } })?.response?.data
    ?.message
  if (serverMessage) return serverMessage
  return err instanceof Error ? err.message : '导入失败'
}

async function submitUploadImport(): Promise<number> {
  if (!importForm.name.trim()) {
    ElMessage.warning('请填写词典名称')
    throw new Error('请填写词典名称')
  }
  if (uploadFileList.value.length === 0) {
    ElMessage.warning('请选择要上传的词典文件')
    throw new Error('请选择要上传的词典文件')
  }
  const form = new FormData()
  form.append('name', importForm.name)
  form.append('format', importForm.format)
  form.append('lang_from', importForm.lang_from)
  form.append('lang_to', importForm.lang_to)
  uploadFileList.value.forEach((file) => form.append('files', file))
  return (await dictApi.uploadDictionary(form)).task_id
}

// 逐部串行导入：避免争抢 SQLite 写锁，且每部有独立的成功/失败状态
async function submitBatchImport() {
  const selected = dictsDirDictionaries.value.filter((group) =>
    selectedGroupKeys.value.includes(group.key),
  )
  if (selected.length === 0) {
    ElMessage.warning('请选择要导入的词典')
    return
  }

  importing.value = true
  batchRunning.value = true
  batchCancelled.value = false
  batchSummary.value = ''
  let succeeded = 0
  let failed = 0
  try {
    for (const group of selected) {
      if (batchCancelled.value) break
      const name = (groupNames[group.key] ?? '').trim()
      if (!name) {
        groupStatus[group.key] = 'error'
        groupError[group.key] = '请填写词典名称'
        failed += 1
        continue
      }
      groupStatus[group.key] = 'importing'
      delete groupError[group.key]
      try {
        // 不传语言方向：由服务端按词头/释义的文字种类自动识别
        const { task_id: taskId } = await dictApi.importFromDictsDir({
          name,
          format: group.format,
          skip_resources: skipResources.value,
          files: group.files.map((file) => file.relpath),
        })
        const task = await waitForImportTask(taskId)
        groupStatus[group.key] = 'success'
        const from = resultString(task, 'lang_from')
        const to = resultString(task, 'lang_to')
        groupLangs[group.key] = from && to ? `${langLabel(from)} → ${langLabel(to)}` : ''
        groupWordCounts[group.key] = resultNumber(task, 'word_count') ?? 0
        succeeded += 1
        // 就地标记已导入而不重新扫描，否则刚识别出的语言方向会被刷掉
        const index = dictsDirDictionaries.value.findIndex((item) => item.key === group.key)
        if (index !== -1) {
          dictsDirDictionaries.value[index] = { ...group, imported: true }
        }
        selectedGroupKeys.value = selectedGroupKeys.value.filter((key) => key !== group.key)
      } catch (err) {
        if (err instanceof PollAbortedError) break
        groupStatus[group.key] = 'error'
        groupError[group.key] = errorMessage(err)
        failed += 1
      }
    }
    if (unmounted) return
    await loadDictionaries()
    batchSummary.value = `本次导入：成功 ${succeeded} 部，失败 ${failed} 部`
    if (failed === 0) {
      ElMessage.success(`批量导入完成，共导入 ${succeeded} 部词典`)
    }
  } finally {
    importing.value = false
    batchRunning.value = false
  }
}

async function submitImport() {
  if (importMode.value === 'dicts-dir') {
    await submitBatchImport()
    return
  }
  importing.value = true
  try {
    const task = await waitForImportTask(await submitUploadImport())
    await loadDictionaries()
    ElMessage.success(`导入成功，共 ${resultNumber(task, 'word_count') ?? 0} 条词条`)
    importDialogVisible.value = false
  } catch (err) {
    // axios 错误已由响应拦截器提示，这里只处理任务失败抛出的 Error
    if (
      !(err instanceof PollAbortedError) &&
      !(err as { isAxiosError?: boolean } | null)?.isAxiosError
    ) {
      ElMessage.error(err instanceof Error ? err.message : '导入失败')
    }
  } finally {
    importing.value = false
  }
}

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
      <el-button type="primary" @click="openImportDialog">导入词典</el-button>
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

    <el-dialog
      v-model="importDialogVisible"
      title="导入词典"
      width="var(--size-dialog-md)"
      :close-on-click-modal="!batchRunning"
      :close-on-press-escape="!batchRunning"
      :show-close="!batchRunning"
    >
      <el-tabs :model-value="importMode" @tab-change="handleTabChange">
        <el-tab-pane label="上传文件" name="upload" />
        <el-tab-pane label="从服务器目录导入" name="dicts-dir" />
      </el-tabs>

      <el-form label-position="top">
        <template v-if="importMode === 'upload'">
          <el-form-item label="词典名称">
            <el-input v-model="importForm.name" placeholder="如：牛津高阶英汉双解词典" />
          </el-form-item>
          <el-form-item label="格式">
            <el-select v-model="importForm.format" style="width: 100%">
              <el-option label="MDict" value="mdict" />
              <el-option label="StarDict" value="stardict" />
              <el-option label="ECDICT" value="ecdict" />
            </el-select>
          </el-form-item>
          <div class="lang-row">
            <el-form-item label="源语言">
              <el-select v-model="importForm.lang_from" style="width: 100%">
                <el-option
                  v-for="opt in LANGUAGE_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="目标语言">
              <el-select v-model="importForm.lang_to" style="width: 100%">
                <el-option
                  v-for="opt in LANGUAGE_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </div>

          <el-form-item
            :label="
              isSingleFileFormat
                ? '词典文件（ECDICT 只能选 1 个 CSV）'
                : '词典文件（可多选，如 .mdx + .mdd）'
            "
          >
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              :multiple="!isSingleFileFormat"
              @change="handleFileChange"
            >
              <el-button>选择文件</el-button>
            </el-upload>
            <ul class="file-list">
              <li v-for="(file, i) in uploadFileList" :key="i">
                {{ file.name }}
                <button type="button" class="remove-btn" @click="removeUploadFile(i)">×</button>
              </li>
            </ul>
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item label="服务器 /data/dicts 目录">
            <div class="dicts-dir-browser">
              <div class="dicts-dir-path">
                <el-icon
                  class="path-icon"
                  :class="{ disabled: !dictsDirPath }"
                  title="回到根目录 /data/dicts"
                  @click="goToDictsDirRoot"
                >
                  <HomeFilled />
                </el-icon>
                <el-icon
                  class="path-icon"
                  :class="{ disabled: !dictsDirPath }"
                  title="返回上一级目录"
                  @click="goToDictsDirParent"
                >
                  <Back />
                </el-icon>
                <span class="path-text"
                  >/data/dicts{{ dictsDirPath ? '/' + dictsDirPath : '' }}</span
                >
              </div>
              <div class="dir-options">
                <el-checkbox
                  v-model="dictsDirRecursive"
                  :disabled="batchRunning"
                  @change="toggleRecursive"
                  >包含子目录</el-checkbox
                >
                <el-checkbox v-model="skipResources" :disabled="batchRunning"
                  >不导入发音/图片（省空间）</el-checkbox
                >
              </div>
              <p class="hint">
                已自动识别词典，格式与名称都已填好（名称可改）。语言方向在导入时按词头/释义的文字种类自动识别，导入后可在词典列表里编辑修正。
              </p>
              <div class="dicts-dir-scroll">
                <template v-if="!dictsDirRecursive">
                  <div
                    v-for="dir in dictsDirDirectories"
                    :key="dir.name"
                    class="dir-row"
                    @click="openDictsDirEntry(dir)"
                  >
                    <el-icon class="dir-icon"><Folder /></el-icon>{{ dir.name }}
                  </div>
                </template>

                <div v-if="dictsDirDictionaries.length" class="group-toolbar">
                  <el-checkbox
                    :model-value="allGroupsSelected"
                    :indeterminate="someGroupsSelected"
                    :disabled="batchRunning"
                    @change="toggleAllGroups"
                    >全选</el-checkbox
                  >
                  <span class="hint"
                    >识别到 {{ dictsDirDictionaries.length }} 部，已选
                    {{ selectedGroupKeys.length }} 部 · {{ formatSize(selectedTotalSize)
                    }}<template v-if="skipResources"
                      >（源文件体积；勾了不导入发音/图片，实际占用远小于此）</template
                    ></span
                  >
                </div>

                <el-checkbox-group v-model="selectedGroupKeys" class="dicts-dir-options">
                  <div v-for="group in dictsDirDictionaries" :key="group.key" class="group-row">
                    <el-checkbox
                      :value="group.key"
                      :disabled="!group.importable || batchRunning"
                      :title="group.reason ?? ''"
                      :aria-label="`选择 ${groupNames[group.key] || group.name}`"
                    />
                    <el-input
                      v-model="groupNames[group.key]"
                      size="small"
                      class="group-name"
                      :disabled="!group.importable || batchRunning"
                      placeholder="词典名称"
                    />
                    <el-tag size="small">{{ FORMAT_LABELS[group.format] }}</el-tag>
                    <el-popover placement="top" trigger="hover" width="var(--size-popover-md)">
                      <template #reference>
                        <span class="hint group-files"
                          >{{ group.files.length }} 个文件 ·
                          {{ formatSize(group.total_size) }}</span
                        >
                      </template>
                      <ul class="group-file-list">
                        <li v-for="file in group.files" :key="file.relpath">
                          {{ file.relpath
                          }}<span v-if="file.imported" class="hint"> （已导入）</span>
                        </li>
                      </ul>
                    </el-popover>
                    <el-tag size="small" class="group-status" :type="groupStatusTagType(group)">{{
                      groupStatusLabel(group)
                    }}</el-tag>
                    <span v-if="groupLangs[group.key]" class="hint group-result">
                      {{ groupLangs[group.key] }} · {{ groupWordCounts[group.key] }} 条
                    </span>
                    <el-popover
                      v-if="dictsDirRecursive"
                      placement="top"
                      trigger="hover"
                      width="var(--size-popover-md)"
                    >
                      <template #reference>
                        <span class="hint group-dir">{{ group.dir || '/data/dicts' }}</span>
                      </template>
                      <span>{{ group.dir || '/data/dicts' }}</span>
                    </el-popover>
                  </div>
                </el-checkbox-group>

                <p v-if="dictsDirDictionaries.length === 0" class="hint">
                  {{
                    dictsDirRecursive
                      ? '该目录及其子目录下都没有识别到词典文件。'
                      : '当前目录下未识别到词典文件，请先将词典文件放入该目录（可进入子目录继续查看）。'
                  }}
                </p>
                <el-popover
                  v-if="dictsDirSkipped.length"
                  placement="top"
                  trigger="hover"
                  width="var(--size-popover-lg)"
                >
                  <template #reference>
                    <p class="hint skipped-hint">
                      已忽略 {{ dictsDirSkipped.length }} 个与词典无关的文件
                    </p>
                  </template>
                  <ul class="group-file-list">
                    <li v-for="name in dictsDirSkipped" :key="name">{{ name }}</li>
                  </ul>
                </el-popover>
              </div>
              <p v-if="batchSummary" class="hint batch-summary">{{ batchSummary }}</p>
              <p v-if="importedSources.files.length" class="hint source-note">
                本次导入的词典已写入数据库，其中 {{ importedSources.files.length }} 个源文件（{{
                  formatSize(importedSources.size)
                }}）已不再被查词读取
                <el-popover placement="top" trigger="hover" width="var(--size-popover-lg)">
                  <template #reference>
                    <span class="source-paths">查看列表</span>
                  </template>
                  <ul class="group-file-list">
                    <li v-for="path in importedSources.files" :key="path">{{ path }}</li>
                  </ul>
                </el-popover>
                ；确认另有备份后可自行删除以释放空间（本程序不会自动删除任何文件）。
              </p>
            </div>
          </el-form-item>
        </template>
      </el-form>

      <template #footer>
        <el-button v-if="batchRunning" @click="batchCancelled = true">停止导入剩余</el-button>
        <el-button :disabled="batchRunning" @click="importDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="importMode === 'dicts-dir' && scanning"
          @click="submitImport"
        >
          {{ importMode === 'dicts-dir' ? '批量导入' : '开始导入' }}
        </el-button>
      </template>
    </el-dialog>

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

.lang-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}

.file-list {
  list-style: none;
  padding: 0;
  margin: var(--space-2) 0 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.file-list li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.dicts-dir-browser {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.dicts-dir-path {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--color-border);
}

.path-icon {
  color: var(--color-text-secondary);
  cursor: pointer;
}

.path-icon:hover {
  color: var(--color-brand-600);
}

.path-icon.disabled {
  color: var(--color-text-tertiary);
  cursor: default;
  pointer-events: none;
}

.path-text {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-family: var(--font-family-mono);
  overflow-wrap: anywhere;
}

.dicts-dir-scroll {
  max-height: var(--size-scroll-sm);
  overflow-y: auto;
}

.dicts-dir-options {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
}

.group-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-1) 0;
  /* 同 .dir-row：需显式恢复 el-checkbox-group 重置的 font-size/line-height */
  font-size: var(--text-base);
  line-height: 1;
}

.group-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  font-size: var(--text-base);
  line-height: 1;
}

.group-name {
  /* 一次性尺寸：名称输入框的弹性宽度，窄了才换行 */
  flex: 1 1 160px;
  min-width: 120px;
}

.group-files,
.group-status,
.group-result,
.group-dir {
  flex-shrink: 0;
}

.group-dir {
  /* 一次性尺寸：目录列超出省略，完整路径见 popover */
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
}

.dir-options {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
  font-size: var(--text-base);
  line-height: 1;
}

.source-note {
  margin-top: var(--space-2);
}

.source-paths {
  color: var(--color-brand-600);
  cursor: default;
  text-decoration: underline;
}

.skipped-hint {
  cursor: default;
}

.group-files {
  cursor: default;
}

.group-file-list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  overflow-wrap: anywhere;
}

.batch-summary {
  margin-top: var(--space-2);
}

.dir-row {
  display: flex;
  align-items: center;
  height: var(--size-control-md);
  /* el-checkbox-group 把 font-size/line-height 重置成 0，普通 div 需显式恢复，否则图标与文字塌缩 */
  font-size: var(--text-base);
  line-height: 1;
  color: var(--color-text-primary);
  cursor: pointer;
}

.dir-row:hover {
  color: var(--color-brand-600);
}

.dir-icon {
  margin-right: var(--space-1);
  color: var(--color-text-secondary);
  vertical-align: -0.15em;
}

.remove-btn {
  border: none;
  background: none;
  color: var(--color-danger);
  cursor: pointer;
  font-size: var(--text-base);
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
