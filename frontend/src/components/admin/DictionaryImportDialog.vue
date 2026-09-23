<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as dictApi from '../../api/admin/dictionaries'
import {
  PollAbortedError,
  isAxiosError,
  resultNumber,
  useImportTask,
} from '../../composables/useImportTask'
import { LANGUAGE_OPTIONS } from '../../utils/language'
import type { DictionaryFormat } from '../../types/dictionary'
import DictsDirImportPanel from './DictsDirImportPanel.vue'

const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ imported: [] }>()

const { waitForImportTask } = useImportTask()

const importMode = ref<'upload' | 'dicts-dir'>('upload')
const dirsPanel = ref<InstanceType<typeof DictsDirImportPanel> | null>(null)
const uploading = ref(false)
const importForm = reactive({
  name: '',
  format: 'ecdict' as DictionaryFormat,
  lang_from: 'en',
  lang_to: 'zh-Hans',
})
const uploadFileList = ref<File[]>([])

// ECDICT 一个 CSV 就是一部词典，后端拒绝多选，界面直接限制为单选
const isSingleFileFormat = computed(() => importForm.format === 'ecdict')

const batchRunning = computed(() => dirsPanel.value?.running ?? false)
const dirsScanning = computed(() => dirsPanel.value?.scanning ?? false)

// 切换格式后旧的文件选择不再适用，清空
watch(
  () => importForm.format,
  () => {
    uploadFileList.value = []
  },
)

watch(visible, (open) => {
  if (!open) return
  importForm.name = ''
  importForm.format = 'ecdict'
  importForm.lang_from = 'en'
  importForm.lang_to = 'zh-Hans'
  uploadFileList.value = []
  importMode.value = 'upload'
})

function handleTabChange(name: string | number) {
  importMode.value = name === 'dicts-dir' ? 'dicts-dir' : 'upload'
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

async function submitUpload() {
  if (!importForm.name.trim()) {
    ElMessage.warning('请填写词典名称')
    return
  }
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

  uploading.value = true
  try {
    const { task_id: taskId } = await dictApi.uploadDictionary(form)
    const task = await waitForImportTask(taskId)
    emit('imported')
    ElMessage.success(`导入成功，共 ${resultNumber(task, 'word_count') ?? 0} 条词条`)
    visible.value = false
  } catch (err) {
    // axios 错误已由响应拦截器提示，这里只处理任务失败抛出的 Error
    if (!(err instanceof PollAbortedError) && !isAxiosError(err)) {
      ElMessage.error(err instanceof Error ? err.message : '导入失败')
    }
  } finally {
    uploading.value = false
  }
}

async function submit() {
  if (importMode.value === 'dicts-dir') {
    await dirsPanel.value?.submit()
    return
  }
  await submitUpload()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="导入词典"
    width="var(--size-dialog-md)"
    :close-on-click-modal="!batchRunning"
    :close-on-press-escape="!batchRunning"
    :show-close="!batchRunning"
  >
    <el-tabs :model-value="importMode" @tab-change="handleTabChange">
      <el-tab-pane label="上传文件" name="upload" :disabled="batchRunning" />
      <el-tab-pane label="从服务器目录导入" name="dicts-dir" :disabled="batchRunning" />
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
              : '词典文件（可多选：.mdx + .mdd，以及同目录的 .css / 字体）'
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
      <DictsDirImportPanel v-else ref="dirsPanel" @imported="emit('imported')" />
    </el-form>

    <template #footer>
      <el-button v-if="batchRunning" @click="dirsPanel?.cancel()">停止导入剩余</el-button>
      <el-button :disabled="batchRunning" @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="uploading || batchRunning"
        :disabled="importMode === 'dicts-dir' && dirsScanning"
        @click="submit"
      >
        {{ importMode === 'dicts-dir' ? '批量导入' : '开始导入' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
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

.remove-btn {
  border: none;
  background: none;
  color: var(--color-danger);
  cursor: pointer;
  font-size: var(--text-base);
}
</style>
