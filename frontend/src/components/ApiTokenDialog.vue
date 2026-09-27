<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getApiToken, issueApiToken } from '../api/auth'
import { copyText } from '../utils/clipboard'

const visible = defineModel<boolean>('visible', { required: true })

const token = ref<string | null>(null)
const loading = ref(false)
const issuing = ref(false)

watch(visible, async (open) => {
  if (!open) return
  loading.value = true
  try {
    token.value = (await getApiToken()).api_token
  } finally {
    loading.value = false
  }
})

async function issue() {
  if (token.value) {
    try {
      await ElMessageBox.confirm(
        '重新分配后当前 Token 立即失效，正在使用它的工具需要换成新的。',
        '重新分配 Token',
        { type: 'warning', confirmButtonText: '重新分配' },
      )
    } catch {
      return
    }
  }
  issuing.value = true
  try {
    token.value = (await issueApiToken()).api_token
    ElMessage.success('Token 已分配')
  } finally {
    issuing.value = false
  }
}

async function copy() {
  if (!token.value) return
  if (await copyText(token.value)) ElMessage.success('已复制到剪贴板')
  else ElMessage.warning('复制失败，请手动选中文本复制')
}
</script>

<template>
  <el-dialog v-model="visible" title="Token 管理" width="var(--size-dialog-sm)">
    <div v-loading="loading" class="body">
      <p class="hint">
        用这个 Token 调用对外 API（请求头 <code>Authorization: Bearer &lt;Token&gt;</code>）即以你的身份查询：
        受你的可用词典限制，查询计入你的历史，收藏进你的生词本。
      </p>
      <template v-if="token">
        <code class="token">{{ token }}</code>
        <div class="actions">
          <el-button @click="copy">复制</el-button>
          <el-button :loading="issuing" @click="issue">重新分配</el-button>
        </div>
      </template>
      <template v-else-if="!loading">
        <p class="empty">你还没有 Token。</p>
        <div class="actions">
          <el-button type="primary" :loading="issuing" @click="issue">分配</el-button>
        </div>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-height: var(--size-control-lg);
}

.hint {
  margin: 0;
  font-size: var(--text-sm);
  line-height: var(--leading-body);
  color: var(--color-text-secondary);
}

.hint code {
  font-family: var(--font-family-mono);
  font-size: var(--text-xs);
}

.token {
  display: block;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-bg-base);
  font-family: var(--font-family-mono);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  word-break: break-all;
}

.empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
