<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as userApi from '../../api/admin/users'
import RefreshButton from '../../components/admin/RefreshButton.vue'
import type { AdminUserDetail, AdminUserItem } from '../../types/adminUser'

const users = ref<AdminUserItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const search = ref('')
const statusFilter = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const resp = await userApi.listUsers(search.value, statusFilter.value, page.value, pageSize)
    users.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(page, load)
watch(statusFilter, () => {
  page.value = 1
  load()
})

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})

// --- 添加用户 ---
const createVisible = ref(false)
const createLoading = ref(false)
const createForm = reactive({ username: '', email: '' })

function openCreate() {
  createForm.username = ''
  createForm.email = ''
  createVisible.value = true
}

async function submitCreate() {
  const username = createForm.username.trim()
  if (username.length < 3) {
    ElMessage.warning('用户名至少 3 位')
    return
  }
  createLoading.value = true
  try {
    const { temporary_password } = await userApi.createUser(
      username,
      createForm.email.trim() || undefined,
    )
    createVisible.value = false
    tempPasswordUsername.value = username
    tempPasswordValue.value = temporary_password
    tempPasswordVisible.value = true
    page.value = 1
    await load()
  } finally {
    createLoading.value = false
  }
}

async function toggleStatus(user: AdminUserItem) {
  const updated =
    user.status === 'active'
      ? await userApi.disableUser(user.id)
      : await userApi.enableUser(user.id)
  const index = users.value.findIndex((u) => u.id === user.id)
  if (index !== -1) users.value[index] = updated
}

async function resetPassword(user: AdminUserItem) {
  try {
    await ElMessageBox.confirm(`确认为「${user.username}」生成临时密码？`, '重置密码', {
      type: 'warning',
      confirmButtonText: '生成',
    })
  } catch {
    return
  }
  const { temporary_password } = await userApi.resetUserPassword(user.id)
  tempPasswordUsername.value = user.username
  tempPasswordValue.value = temporary_password
  tempPasswordVisible.value = true
}

const tempPasswordVisible = ref(false)
const tempPasswordUsername = ref('')
const tempPasswordValue = ref('')

async function copyTempPassword() {
  try {
    await navigator.clipboard.writeText(tempPasswordValue.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选中复制')
  }
}

// --- 详情 ---
const detailVisible = ref(false)
const detail = ref<AdminUserDetail | null>(null)

async function openDetail(user: AdminUserItem) {
  detail.value = await userApi.getUserDetail(user.id)
  detailVisible.value = true
}

function formatDate(value: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div class="title-row">
        <h1>用户管理</h1>
        <RefreshButton :loading="loading" @refresh="load" />
      </div>
      <div class="filters">
        <el-input v-model="search" placeholder="搜索用户名/邮箱" clearable style="width: 200px" />
        <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 140px">
          <el-option label="正常" value="active" />
          <el-option label="禁用" value="disabled" />
        </el-select>
      </div>
    </div>

    <div class="table-toolbar">
      <el-button type="primary" @click="openCreate">添加用户</el-button>
    </div>

    <div v-loading="loading" class="user-list">
      <div class="user-list-header">
        <span>用户名</span>
        <span>邮箱</span>
        <span>注册时间</span>
        <span>最近登录</span>
        <span>生词/查询</span>
        <span>状态</span>
        <span class="col-actions">操作</span>
      </div>
      <div v-for="user in users" :key="user.id" class="user-row">
        <span>{{ user.username }}</span>
        <span>{{ user.email ?? '—' }}</span>
        <span>{{ formatDate(user.created_at) }}</span>
        <span>{{ formatDate(user.last_login_at) }}</span>
        <span>{{ user.vocab_count }} / {{ user.query_count }}</span>
        <span>
          <el-tag :type="user.status === 'active' ? 'success' : 'info'" size="small">
            {{ user.status === 'active' ? '正常' : '禁用' }}
          </el-tag>
        </span>
        <span class="col-actions">
          <el-button text @click="openDetail(user)">详情</el-button>
          <el-button text @click="resetPassword(user)">重置密码</el-button>
          <el-button
            text
            :type="user.status === 'active' ? 'danger' : 'primary'"
            @click="toggleStatus(user)"
          >
            {{ user.status === 'active' ? '禁用' : '启用' }}
          </el-button>
        </span>
      </div>
      <div v-if="!loading && users.length === 0" class="empty">没有符合条件的用户。</div>
    </div>

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next"
      class="pagination"
    />

    <el-dialog v-model="detailVisible" title="用户详情" width="560px">
      <template v-if="detail">
        <h3>{{ detail.user.username }}</h3>
        <p class="hint">
          邮箱：{{ detail.user.email ?? '—' }} · 注册于 {{ formatDate(detail.user.created_at) }}
        </p>

        <h4>生词本（{{ detail.vocab_items.length }}）</h4>
        <ul v-if="detail.vocab_items.length" class="detail-list">
          <li v-for="item in detail.vocab_items" :key="item.id">
            <strong>{{ item.word }}</strong>
            <span v-if="item.phonetic"> [{{ item.phonetic }}]</span>
          </li>
        </ul>
        <p v-else class="hint">暂无生词</p>

        <h4>最近查询</h4>
        <ul v-if="detail.recent_queries.length" class="detail-list">
          <li v-for="(q, i) in detail.recent_queries" :key="i">
            {{ q.word }}
            <span class="hint">（{{ q.status }} · {{ formatDate(q.created_at) }}）</span>
          </li>
        </ul>
        <p v-else class="hint">暂无查询记录</p>
      </template>
    </el-dialog>

    <el-dialog v-model="createVisible" title="添加用户" width="420px">
      <el-form :model="createForm" label-position="top" @submit.prevent="submitCreate">
        <el-form-item label="用户名">
          <el-input v-model="createForm.username" placeholder="至少 3 位" />
        </el-form-item>
        <el-form-item label="邮箱（可选）">
          <el-input v-model="createForm.email" placeholder="user@example.com" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createLoading" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="tempPasswordVisible" title="临时密码已生成" width="420px">
      <p class="hint">请将以下临时密码告知「{{ tempPasswordUsername }}」，建议其登录后立即修改：</p>
      <div class="reveal-token">
        <code>{{ tempPasswordValue }}</code>
        <el-button size="small" @click="copyTempPassword">复制</el-button>
      </div>
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
  flex-wrap: wrap;
  gap: var(--space-3);
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

.filters {
  display: flex;
  gap: var(--space-3);
}

.table-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-3);
}

.user-list {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  overflow: hidden;
}

.user-list-header,
.user-row {
  display: grid;
  grid-template-columns: 1fr 1.4fr 1fr 1fr 0.9fr 0.8fr 1.6fr;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
}

.user-list-header {
  background: var(--color-bg-base);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.user-row {
  border-top: 1px solid var(--color-border);
  color: var(--color-text-primary);
}

.user-row:hover {
  background: var(--color-hover-tint);
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

.empty {
  padding: var(--space-7);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.pagination {
  margin-top: var(--space-5);
  justify-content: center;
}

.hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.detail-list {
  list-style: none;
  padding: 0;
  margin: var(--space-2) 0 var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  max-height: 160px;
  overflow-y: auto;
}

.reveal-token {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: var(--color-bg-base);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}

.reveal-token code {
  flex: 1;
  font-family: ui-monospace, monospace;
  font-size: var(--text-sm);
}
</style>
