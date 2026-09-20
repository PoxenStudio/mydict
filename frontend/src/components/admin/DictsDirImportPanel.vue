<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Back, Folder, HomeFilled } from '@element-plus/icons-vue'
import * as dictApi from '../../api/admin/dictionaries'
import {
  PollAbortedError,
  errorMessage,
  resultNumber,
  resultString,
  useImportTask,
} from '../../composables/useImportTask'
import { langLabel } from '../../utils/language'
import { formatSize } from '../../utils/format'
import type {
  DictionaryFormat,
  DictsDirFile,
  DictsDirGroup,
  DictsDirListing,
} from '../../types/dictionary'

const emit = defineEmits<{ imported: [] }>()

type GroupImportStatus = 'pending' | 'imported' | 'importing' | 'success' | 'error' | 'blocked'

const FORMAT_LABELS: Record<DictionaryFormat, string> = {
  mdict: 'MDict',
  stardict: 'StarDict',
  ecdict: 'ECDICT',
}

const { waitForImportTask, isUnmounted } = useImportTask()

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

async function submit() {
  const selected = dictsDirDictionaries.value.filter((group) =>
    selectedGroupKeys.value.includes(group.key),
  )
  if (selected.length === 0) {
    ElMessage.warning('请选择要导入的词典')
    return
  }

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
    if (isUnmounted()) return
    emit('imported')
    batchSummary.value = `本次导入：成功 ${succeeded} 部，失败 ${failed} 部`
    if (failed === 0) {
      ElMessage.success(`批量导入完成，共导入 ${succeeded} 部词典`)
    }
  } finally {
    batchRunning.value = false
  }
}

function cancel() {
  batchCancelled.value = true
}

onMounted(() => loadDictsDirScan(''))

defineExpose({ submit, cancel, running: batchRunning, scanning })
</script>

<template>
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
        <span class="path-text">/data/dicts{{ dictsDirPath ? '/' + dictsDirPath : '' }}</span>
      </div>
      <div class="dir-options">
        <el-checkbox v-model="dictsDirRecursive" :disabled="batchRunning" @change="toggleRecursive"
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
            >识别到 {{ dictsDirDictionaries.length }} 部，已选 {{ selectedGroupKeys.length }} 部 ·
            {{ formatSize(selectedTotalSize)
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
                  >{{ group.files.length }} 个文件 · {{ formatSize(group.total_size) }}</span
                >
              </template>
              <ul class="group-file-list">
                <li v-for="file in group.files" :key="file.relpath">
                  {{ file.relpath }}<span v-if="file.imported" class="hint"> （已导入）</span>
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
            <p class="hint skipped-hint">已忽略 {{ dictsDirSkipped.length }} 个与词典无关的文件</p>
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

<style scoped>
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

.hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}
</style>
