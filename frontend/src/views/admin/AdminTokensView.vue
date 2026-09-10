<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as tokenApi from '../../api/admin/tokens'
import type { ApiTokenItem } from '../../types/token'

const tokens = ref<ApiTokenItem[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    tokens.value = await tokenApi.listTokens()
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function toggleStatus(token: ApiTokenItem) {
  const updated =
    token.status === 'active'
      ? await tokenApi.disableToken(token.id)
      : await tokenApi.enableToken(token.id)
  const index = tokens.value.findIndex((t) => t.id === token.id)
  if (index !== -1) tokens.value[index] = updated
}

async function regenerate(token: ApiTokenItem) {
  try {
    await ElMessageBox.confirm(
      `重新生成后，旧 Token「${token.token_prefix}」将立即失效，确认继续？`,
      '重新生成 Token',
      { type: 'warning', confirmButtonText: '重新生成' },
    )
  } catch {
    return
  }
  const result = await tokenApi.regenerateToken(token.id)
  showRevealDialog(result.name, result.token)
  load()
}

const vocabCountVisible = ref(false)
const vocabCountValue = ref(0)
const vocabCountTokenName = ref('')

async function showVocabCount(token: ApiTokenItem) {
  const { count } = await tokenApi.getTokenVocabCount(token.id)
  vocabCountValue.value = count
  vocabCountTokenName.value = token.name
  vocabCountVisible.value = true
}

// --- 新建 Token ---
const createDialogVisible = ref(false)
const createForm = reactive({ name: '', dailyLimit: undefined as number | undefined })
const creating = ref(false)

function openCreateDialog() {
  createForm.name = ''
  createForm.dailyLimit = undefined
  createDialogVisible.value = true
}

async function submitCreate() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请填写 Token 名称/用途备注')
    return
  }
  creating.value = true
  try {
    const result = await tokenApi.createToken(createForm.name, createForm.dailyLimit ?? null)
    createDialogVisible.value = false
    tokens.value.unshift(result)
    showRevealDialog(result.name, result.token)
  } finally {
    creating.value = false
  }
}

// --- 明文一次性展示 ---
const revealVisible = ref(false)
const revealName = ref('')
const revealToken = ref('')

function showRevealDialog(name: string, token: string) {
  revealName.value = name
  revealToken.value = token
  revealVisible.value = true
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(revealToken.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选中复制')
  }
}

function formatDate(value: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Token 管理</h1>
      <el-button type="primary" @click="openCreateDialog">新建 Token</el-button>
    </div>

    <div v-loading="loading" class="token-list">
      <div class="token-list-header">
        <span>名称</span>
        <span>Token</span>
        <span>每日上限</span>
        <span>今日/累计</span>
        <span>最后调用</span>
        <span>状态</span>
        <span class="col-actions">操作</span>
      </div>
      <div v-for="token in tokens" :key="token.id" class="token-row">
        <span>{{ token.name }}</span>
        <span class="mono">{{ token.token_prefix }}</span>
        <span>{{ token.daily_limit ?? '系统默认' }}</span>
        <span>{{ token.today_count }} / {{ token.total_count }}</span>
        <span>{{ formatDate(token.last_used_at) }}</span>
        <span>
          <el-tag :type="token.status === 'active' ? 'success' : 'info'" size="small">
            {{ token.status === 'active' ? '启用' : '禁用' }}
          </el-tag>
        </span>
        <span class="col-actions">
          <el-button text @click="showVocabCount(token)">收藏数</el-button>
          <el-button text @click="regenerate(token)">重新生成</el-button>
          <el-button
            text
            :type="token.status === 'active' ? 'danger' : 'primary'"
            @click="toggleStatus(token)"
          >
            {{ token.status === 'active' ? '禁用' : '启用' }}
          </el-button>
        </span>
      </div>
      <div v-if="!loading && tokens.length === 0" class="empty">暂无 Token，点击右上角新建。</div>
    </div>

    <el-dialog v-model="createDialogVisible" title="新建 Token" width="420px">
      <el-form label-position="top">
        <el-form-item label="名称/用途备注">
          <el-input v-model="createForm.name" placeholder="如：XX浏览器插件" />
        </el-form-item>
        <el-form-item label="每日调用上限（留空则使用系统默认值）">
          <el-input-number v-model="createForm.dailyLimit" :min="1" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="revealVisible" title="Token 已生成" width="480px">
      <p class="reveal-hint">「{{ revealName }}」的完整 Token 仅在此展示一次，请立即复制保存：</p>
      <div class="reveal-token">
        <code>{{ revealToken }}</code>
        <el-button size="small" @click="copyToken">复制</el-button>
      </div>
      <template #footer>
        <el-button type="primary" @click="revealVisible = false">我已保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="vocabCountVisible" title="Token 收藏统计" width="360px">
      <p>「{{ vocabCountTokenName }}」当前收藏 {{ vocabCountValue }} 条生词。</p>
      <p class="hint">仅统计数量，收藏内容不在后台展示，如需人工核查请直接查数据库或导出。</p>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
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

.token-list {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  overflow: hidden;
}

.token-list-header,
.token-row {
  display: grid;
  grid-template-columns: 1.4fr 1.2fr 1fr 1fr 1.2fr 0.8fr 1.6fr;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
}

.token-list-header {
  background: var(--color-bg-base);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.token-row {
  border-top: 1px solid var(--color-border);
  color: var(--color-text-primary);
}

.token-row:hover {
  background: var(--color-brand-50);
}

.mono {
  font-family: ui-monospace, monospace;
  color: var(--color-text-secondary);
}

.col-actions {
  text-align: right;
}

.empty {
  padding: var(--space-7);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.reveal-hint {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.reveal-token {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: var(--color-bg-base);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  word-break: break-all;
}

.reveal-token code {
  flex: 1;
  font-family: ui-monospace, monospace;
  font-size: var(--text-sm);
}

.hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}
</style>
