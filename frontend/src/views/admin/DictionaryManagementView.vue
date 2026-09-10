<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, Document, Folder, HomeFilled } from '@element-plus/icons-vue'
import * as dictApi from '../../api/admin/dictionaries'
import RefreshButton from '../../components/admin/RefreshButton.vue'
import { LANGUAGE_OPTIONS, langLabel } from '../../utils/language'
import type {
  DictionaryFormat,
  DictionaryItem,
  DictsDirFile,
  TestQueryEntry,
} from '../../types/dictionary'

const dictionaries = ref<DictionaryItem[]>([])
const loading = ref(false)

async function loadDictionaries() {
  loading.value = true
  try {
    dictionaries.value = await dictApi.listDictionaries()
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
const importMode = ref<'upload' | 'dicts-dir'>('upload')
const importing = ref(false)
const importForm = reactive({
  name: '',
  format: 'ecdict' as DictionaryFormat,
  lang_from: 'en',
  lang_to: 'zh-Hans',
})
const uploadFileList = ref<File[]>([])
const dictsDirEntries = ref<DictsDirFile[]>([])
const dictsDirPath = ref('')
const selectedDictsDirFiles = ref<string[]>([])
const dictsDirSingleFile = ref('')
// ECDICT 一个 CSV 就是一部完整词典，选多个会被后端拒绝（EcdictParser 只认第一个），
// 界面上直接限制成单选，避免选完提交才报错。
const isSingleFileFormat = computed(() => importForm.format === 'ecdict')

// 切换格式后旧的文件选择大概率不再适用（后缀都对不上），统一清空避免残留无效状态
watch(
  () => importForm.format,
  () => {
    uploadFileList.value = []
    selectedDictsDirFiles.value = []
    dictsDirSingleFile.value = ''
  },
)

// 目录里的选择只在当前目录有效，切到别的目录后沿用旧选择容易造成误解（选中的文件已经
// 看不见了），统一清空
watch(dictsDirPath, () => {
  selectedDictsDirFiles.value = []
  dictsDirSingleFile.value = ''
})

function openImportDialog() {
  importForm.name = ''
  importForm.format = 'ecdict'
  importForm.lang_from = 'en'
  importForm.lang_to = 'zh-Hans'
  uploadFileList.value = []
  selectedDictsDirFiles.value = []
  dictsDirSingleFile.value = ''
  importMode.value = 'upload'
  importDialogVisible.value = true
}

async function loadDictsDirEntries(path: string) {
  const listing = await dictApi.listDictsDirFiles(path)
  dictsDirPath.value = listing.path
  dictsDirEntries.value = listing.entries
}

async function switchToDictsDirTab() {
  importMode.value = 'dicts-dir'
  await loadDictsDirEntries('')
}

function openDictsDirEntry(entry: DictsDirFile) {
  if (!entry.is_dir) return
  loadDictsDirEntries(dictsDirPath.value ? `${dictsDirPath.value}/${entry.name}` : entry.name)
}

function goToDictsDirRoot() {
  if (dictsDirPath.value) loadDictsDirEntries('')
}

function goToDictsDirParent() {
  if (!dictsDirPath.value) return
  const parts = dictsDirPath.value.split('/')
  parts.pop()
  loadDictsDirEntries(parts.join('/'))
}

function handleTabChange(name: string | number) {
  if (name === 'dicts-dir') {
    switchToDictsDirTab()
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

async function submitImport() {
  if (!importForm.name.trim()) {
    ElMessage.warning('请填写词典名称')
    return
  }
  importing.value = true
  try {
    let created: DictionaryItem
    if (importMode.value === 'upload') {
      if (uploadFileList.value.length === 0) {
        ElMessage.warning('请选择要上传的词典文件')
        return
      }
      const form = new FormData()
      form.append('name', importForm.name)
      form.append('format', importForm.format)
      form.append('lang_from', importForm.lang_from)
      form.append('lang_to', importForm.lang_to)
      uploadFileList.value.forEach((file) => form.append('files', file))
      created = await dictApi.uploadDictionary(form)
    } else {
      // 选择结果只是当前目录内的文件名，后端需要相对 /data/dicts 的完整路径才能定位到子目录
      const toFullPath = (name: string) =>
        dictsDirPath.value ? `${dictsDirPath.value}/${name}` : name
      const names = isSingleFileFormat.value
        ? dictsDirSingleFile.value
          ? [dictsDirSingleFile.value]
          : []
        : selectedDictsDirFiles.value
      const files = names.map(toFullPath)
      if (files.length === 0) {
        ElMessage.warning('请选择服务器目录下的词典文件')
        return
      }
      created = await dictApi.importFromDictsDir({
        name: importForm.name,
        format: importForm.format,
        lang_from: importForm.lang_from,
        lang_to: importForm.lang_to,
        files,
      })
    }
    dictionaries.value.push(created)
    ElMessage.success(`导入成功，共 ${created.word_count} 条词条`)
    importDialogVisible.value = false
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

    <div v-loading="loading" class="dict-list">
      <div class="dict-list-header">
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
        draggable="true"
        @dragstart="onDragStart(index)"
        @dragover.prevent
        @drop="onDrop(index)"
      >
        <span class="col-drag" title="拖拽调整顺序">⠿</span>
        <span class="col-name">{{ item.name }}</span>
        <span class="col-format"
          ><el-tag size="small">{{ item.format }}</el-tag></span
        >
        <span class="col-lang">{{ langLabel(item.lang_from) }} → {{ langLabel(item.lang_to) }}</span>
        <span class="col-count">{{ item.word_count }}</span>
        <span class="col-status">
          <el-switch :model-value="item.status === 'enabled'" @change="toggleStatus(item)" />
        </span>
        <span class="col-actions">
          <el-button text @click="openTestQuery(item)">测试查询</el-button>
          <el-button text type="danger" @click="confirmDelete(item)">删除</el-button>
        </span>
      </div>

      <div v-if="!loading && dictionaries.length === 0" class="empty-state">
        暂无词典，点击右上角「导入词典」开始导入。
      </div>
    </div>

    <el-dialog v-model="importDialogVisible" title="导入词典" width="560px">
      <el-tabs :model-value="importMode" @tab-change="handleTabChange">
        <el-tab-pane label="上传文件" name="upload" />
        <el-tab-pane label="从服务器目录导入" name="dicts-dir" />
      </el-tabs>

      <el-form label-position="top">
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

        <template v-if="importMode === 'upload'">
          <el-form-item
            :label="isSingleFileFormat ? '词典文件（ECDICT 只能选 1 个 CSV）' : '词典文件（可多选，如 .mdx + .mdd）'"
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
          <el-form-item
            :label="
              isSingleFileFormat
                ? '选择服务器 /data/dicts 目录下的文件（ECDICT 只能选 1 个）'
                : '选择服务器 /data/dicts 目录下的文件'
            "
          >
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
            <div class="dicts-dir-scroll">
              <el-radio-group v-if="isSingleFileFormat" v-model="dictsDirSingleFile" class="dicts-dir-options">
                <template v-for="f in dictsDirEntries" :key="f.name">
                  <div v-if="f.is_dir" class="dir-row" @click="openDictsDirEntry(f)">
                    <el-icon class="dir-icon"><Folder /></el-icon>{{ f.name }}
                  </div>
                  <el-radio v-else :value="f.name" :disabled="f.imported">
                    <el-icon class="file-icon"><Document /></el-icon>{{ f.name
                    }}<span v-if="f.imported" class="hint"> （已导入）</span>
                  </el-radio>
                </template>
              </el-radio-group>
              <el-checkbox-group v-else v-model="selectedDictsDirFiles" class="dicts-dir-options">
                <template v-for="f in dictsDirEntries" :key="f.name">
                  <div v-if="f.is_dir" class="dir-row" @click="openDictsDirEntry(f)">
                    <el-icon class="dir-icon"><Folder /></el-icon>{{ f.name }}
                  </div>
                  <el-checkbox v-else :value="f.name" :label="f.name" :disabled="f.imported">
                    <el-icon class="file-icon"><Document /></el-icon>{{ f.name
                    }}<span v-if="f.imported" class="hint"> （已导入）</span>
                  </el-checkbox>
                </template>
              </el-checkbox-group>
              <p v-if="dictsDirEntries.length === 0" class="hint">
                当前目录下暂无文件，请先将词典文件放入该目录。
              </p>
            </div>
          </el-form-item>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="testQueryDialogVisible"
      :title="`测试查询 - ${testQueryTarget?.name ?? ''}`"
      width="560px"
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
  max-width: 960px;
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

.dict-list-header,
.dict-row {
  display: grid;
  grid-template-columns: 32px 2fr 1fr 1fr 0.8fr 0.8fr 1.4fr;
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
  font-family: ui-monospace, monospace;
  overflow-wrap: anywhere;
}

.dicts-dir-scroll {
  max-height: 240px;
  overflow-y: auto;
}

.dicts-dir-options {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
}

.dir-row {
  display: flex;
  align-items: center;
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

.file-icon {
  margin-right: var(--space-1);
  color: var(--color-text-tertiary);
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
  max-height: 360px;
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
