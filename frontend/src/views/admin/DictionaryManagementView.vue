<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as dictApi from '../../api/admin/dictionaries'
import { getSpxTranscodeStatus } from '../../api/admin/settings'
import { resultNumber, useImportTask } from '../../composables/useImportTask'
import DictionaryImportDialog from '../../components/admin/DictionaryImportDialog.vue'
import DictionaryRenameDialog from '../../components/admin/DictionaryRenameDialog.vue'
import RefreshButton from '../../components/admin/RefreshButton.vue'
import EntryFrame from '../../components/EntryFrame.vue'
import { LANGUAGE_OPTIONS, langGroupLabel, langGroupOf, langLabel } from '../../utils/language'
import type { DictionaryItem, DictionaryStatus, TestQueryEntry } from '../../types/dictionary'

const dictionaries = ref<DictionaryItem[]>([])
const loading = ref(false)
const renameDialogVisible = ref(false)

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

onMounted(() => {
  loadDictionaries()
  loadSpxStatus()
})

// --- 启用/禁用 ---
async function toggleStatus(item: DictionaryItem) {
  const updated =
    item.status === 'enabled'
      ? await dictApi.disableDictionary(item.id)
      : await dictApi.enableDictionary(item.id)
  const index = dictionaries.value.findIndex((d) => d.id === item.id)
  if (index !== -1) dictionaries.value[index] = updated
}

// --- 语种 tab 与「只看需转码」筛选 ---
const activeLang = ref('all')
const onlyNeedsTranscode = ref(false)

/** tab 计数按**全量**统计——按过滤后的列表算，一点进去计数就归零了 */
const langTabs = computed(() => {
  const counts = new Map<string, number>()
  for (const item of dictionaries.value) {
    const group = langGroupOf(item.lang_from)
    counts.set(group, (counts.get(group) ?? 0) + 1)
  }
  return [
    { value: 'all', label: '全部', count: dictionaries.value.length },
    ...[...counts].map(([group, count]) => ({
      value: group,
      label: langGroupLabel(group),
      count,
    })),
  ]
})

const visibleDictionaries = computed(() =>
  dictionaries.value.filter(
    (item) =>
      (activeLang.value === 'all' || langGroupOf(item.lang_from) === activeLang.value) &&
      (!onlyNeedsTranscode.value || item.spx_pending_count > 0),
  ),
)

// 换筛选条件就清空勾选，否则下一步的批量操作会作用到看不见的行上
watch([activeLang, onlyNeedsTranscode], () => {
  selectedIds.value = []
})

/** 只有「全部」视图且没开需转码筛选时才能拖拽排序。

    排序写的是**全量**顺序，而被过滤掉的行不在视野里——让它拖会把隐藏项的次序一起改乱，
    而「移到哪」在隐藏项存在时本来就没有明确语义。 */
const draggable = computed(() => activeLang.value === 'all' && !onlyNeedsTranscode.value)

// --- 批量启用/停用 ---
const selectedIds = ref<number[]>([])
const statusBatchRunning = ref(false)

const allSelected = computed(
  () =>
    visibleDictionaries.value.length > 0 &&
    visibleDictionaries.value.every((item) => selectedIds.value.includes(item.id)),
)
const someSelected = computed(
  () =>
    !allSelected.value &&
    visibleDictionaries.value.some((item) => selectedIds.value.includes(item.id)),
)

function toggleSelect(id: number) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

function toggleSelectAll(checked: string | number | boolean) {
  selectedIds.value = checked ? visibleDictionaries.value.map((item) => item.id) : []
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

// --- 发音转码 ---
const spxAvailable = ref(false)
const spxRunning = ref(false)
// 从源文件修复（附属资源 + 样式标记）——与发音无关，独立于 spxRunning 免得互相禁用
const resourceRunning = ref(false)

/** 容器里有没有 ffmpeg。没有时「转码」按钮要禁用并说明原因，否则点了只会拿到 422 */
async function loadSpxStatus() {
  try {
    spxAvailable.value = (await getSpxTranscodeStatus()).available
  } catch {
    spxAvailable.value = false
  }
}

const { waitForImportTask } = useImportTask()

/** 扫描发音资源、回填「待转码 .spx 数」；有勾选就只扫勾选的 */
async function scanSpx() {
  const ids = selectedIds.value.length ? [...selectedIds.value] : null
  spxRunning.value = true
  try {
    const { task_id } = await dictApi.scanSpx(ids)
    const task = await waitForImportTask(task_id, 30 * 60 * 1000)
    await loadDictionaries()
    ElMessage.success(`扫描完成，共发现 ${resultNumber(task, 'pending') ?? 0} 个待转发音`)
  } finally {
    spxRunning.value = false
  }
}

/**
 * 从源文件修复：① 补源文件旁边的 CSS/字体/JS/图片；② 展开词条里的 `` `编号` `` 样式标记。
 *
 * 这两样都只存在于源文件里（MDict 把样式表放在 .mdx 同级目录、把标记规则放在 .mdx 头部的
 * StyleSheet 字段），早先的导入都没读，于是存量词典要么缺样式文件、要么把标记原样显示成
 * 排版错乱。这里不用重新导入任何词典；有勾选就只处理勾选的。
 */
async function repairFromSource() {
  const ids = selectedIds.value.length ? [...selectedIds.value] : null
  resourceRunning.value = true
  try {
    const { task_id } = await dictApi.repairFromSource(ids)
    const task = await waitForImportTask(task_id, 30 * 60 * 1000)
    const files = resultNumber(task, 'files') ?? 0
    const styled = resultNumber(task, 'styled_entries') ?? 0
    const parts = [`为 ${resultNumber(task, 'dictionaries') ?? 0} 部词典复制了 ${files} 个文件`]
    if (styled) {
      parts.push(`展开了 ${resultNumber(task, 'styled_dictionaries') ?? 0} 部词典的 ${styled.toLocaleString()} 条样式标记`)
    }
    ElMessage.success(`修复完成：${parts.join('；')}`)
  } finally {
    resourceRunning.value = false
  }
}

/** 批量转码（单部也走这里）。成功后后端会删掉原 .spx。 */
async function transcodeSpx(ids: number[]) {
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(
      `将把 ${ids.length} 部词典里缺少 mp3 的 .spx 发音转成 mp3，**转成功后删除原 .spx**` +
        '（你的源词典文件另有备份，不会丢失）。转码在后端进行，可以关掉页面。',
      '发音转码',
      { type: 'warning', confirmButtonText: '开始转码' },
    )
  } catch {
    return
  }
  spxRunning.value = true
  try {
    const { task_id } = await dictApi.transcodeSpx(ids)
    // 转码是小时级任务（一部大词典可能有几十万个文件），轮询给足时间
    const task = await waitForImportTask(task_id, 6 * 60 * 60 * 1000)
    await loadDictionaries()
    ElMessage.success(
      `转码完成：成功 ${resultNumber(task, 'ok') ?? 0}、失败 ${resultNumber(task, 'failed') ?? 0}`,
    )
  } finally {
    spxRunning.value = false
  }
}

/** 批量栏只对「选中项里真的需要转码的」发起——选了一堆没有 .spx 的不该白跑一趟 */
const transcodeTargetIds = computed(() =>
  visibleDictionaries.value
    .filter((item) => selectedIds.value.includes(item.id) && item.spx_pending_count > 0)
    .map((item) => item.id),
)

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
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div class="title-row">
        <h1>词典管理</h1>
        <RefreshButton :loading="loading" @refresh="loadDictionaries" />
      </div>
      <el-button :loading="spxRunning" @click="scanSpx">扫描发音资源</el-button>
      <el-button :loading="resourceRunning" @click="repairFromSource">从源文件修复</el-button>
      <el-button @click="renameDialogVisible = true">批量重命名</el-button>
      <el-button type="primary" @click="importDialogVisible = true">导入词典</el-button>
    </div>

    <div class="filter-bar">
      <div class="lang-tabs">
        <button
          v-for="tab in langTabs"
          :key="tab.value"
          type="button"
          class="lang-tab"
          :class="{ active: activeLang === tab.value }"
          @click="activeLang = tab.value"
        >
          {{ tab.label }}<span class="tab-count">{{ tab.count }}</span>
        </button>
      </div>
      <label class="need-toggle">
        <el-checkbox v-model="onlyNeedsTranscode" />
        <span>只看需转码</span>
      </label>
    </div>

    <div v-if="selectedIds.length" class="batch-bar">
      <span class="batch-count">已选 {{ selectedIds.length }} 部</span>
      <el-button size="small" :loading="statusBatchRunning" @click="batchSetStatus('enabled')">
        批量启用
      </el-button>
      <el-button size="small" :loading="statusBatchRunning" @click="batchSetStatus('disabled')">
        批量停用
      </el-button>
      <el-button
        size="small"
        type="warning"
        plain
        :loading="spxRunning"
        :disabled="!transcodeTargetIds.length"
        :title="spxAvailable ? '' : '容器里没有 ffmpeg，见「系统设置 → 发音转码」'"
        @click="transcodeSpx(transcodeTargetIds)"
      >
        批量转码（{{ transcodeTargetIds.length }}）
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
        v-for="(item, index) in visibleDictionaries"
        :key="item.id"
        class="dict-row"
        :class="{ selected: selectedIds.includes(item.id) }"
        :draggable="draggable"
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
        <span
          class="col-drag"
          :class="{ disabled: !draggable }"
          :title="draggable ? '拖拽调整顺序' : '筛选状态下不能排序——顺序是全局的'"
          >⠿</span
        >
        <span class="col-name">
          <span class="dict-name-text" :title="item.name">{{ item.name }}</span>
          <el-tag
            v-if="item.spx_pending_count > 0"
            type="warning"
            size="small"
            :title="`还有 ${item.spx_pending_count} 个 .spx 发音没有转码`"
          >
            需转码
          </el-tag>
        </span>
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
          <el-button
            v-if="item.spx_pending_count > 0"
            text
            type="warning"
            :loading="spxRunning"
            :disabled="!spxAvailable"
            :title="spxAvailable ? '' : '容器里没有 ffmpeg，见「系统设置 → 发音转码」'"
            @click="transcodeSpx([item.id])"
          >
            转码
          </el-button>
        </span>
      </div>

      <div v-if="!loading && dictionaries.length === 0" class="empty-state">
        暂无词典，点击右上角「导入词典」开始导入。
      </div>
      <div v-else-if="!loading && visibleDictionaries.length === 0" class="empty-state">
        当前筛选条件下没有词典。
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

    <DictionaryRenameDialog
      v-model="renameDialogVisible"
      :selected-ids="selectedIds"
      @renamed="loadDictionaries"
    />

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
        <div class="test-query-results app-scrollbar">
          <div
            v-for="(entry, i) in testQueryResults"
            :key="`${entry.word}-${i}`"
            class="result-card"
          >
            <div class="result-word">
              {{ entry.word }}
              <span v-if="entry.phonetic" class="result-phonetic">[{{ entry.phonetic }}]</span>
            </div>
            <!--
              用隔离 iframe 而不是 v-html：管理端 token 也在 localStorage 里，直接注入
              第三方词典的 HTML 等于把权限最高的凭证暴露出去（词典的 <style> 还会污染
              整个后台界面）。
            -->
            <EntryFrame
              v-if="testQueryTarget"
              :key="`${entry.word}-${i}`"
              :loader="() => dictApi.getEntryHtml(testQueryTarget!.id, entry.word)"
            />
          </div>
          <p v-if="testQueryWord && testQueryResults.length === 0" class="hint">未查询到结果</p>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  /* 这个列表列最多（勾选/拖拽/名称/格式/语言/词条数/状态/操作），960px 太挤 */
  max-width: var(--size-content-lg);
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
  /* 窄窗口时横向滚动，而不是把 8 列压成不可读——行自己带 min-width */
  overflow-x: auto;
  overflow-y: hidden;
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.lang-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.lang-tab {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  border: none;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.lang-tab:hover {
  background: var(--color-hover-tint);
}

.lang-tab.active {
  background: var(--color-brand-500);
  color: #fff;
}

.tab-count {
  font-size: var(--text-xs);
  opacity: 0.75;
}

.need-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  white-space: nowrap;
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
  /* 名称列与操作列都放宽了：名称后面挂了「需转码」标签，操作列多了「转码」按钮 */
  grid-template-columns:
    var(--size-control-md) var(--size-control-md)
    minmax(0, 2fr) 1fr 1fr 0.8fr 0.8fr minmax(220px, 1.8fr);
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  min-width: 980px;
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

.col-drag.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.col-name {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.dict-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
</style>
