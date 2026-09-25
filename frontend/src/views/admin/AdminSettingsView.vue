<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as settingsApi from '../../api/admin/settings'
import RefreshButton from '../../components/admin/RefreshButton.vue'

const loading = ref(true)
const saving = ref(false)
// 运行时状态而非配置：容器里有没有 ffmpeg、已经转了多少

const form = reactive({
  open_access: false,
  allow_registration: true,
  token_default_daily_limit: 1000,
  anonymous_ip_rate_limit_per_min: 60,
  user_ip_rate_limit_per_min: 120,
  vocab_max_items_per_owner: null as number | null,
  site_name: 'MyDict',
  search_hint_text: '小搜一下, 大进一步',
})

const vocabUnlimited = computed({
  get: () => form.vocab_max_items_per_owner === null,
  set: (unlimited: boolean) => {
    form.vocab_max_items_per_owner = unlimited ? null : 100
  },
})

async function load() {
  loading.value = true
  try {
    Object.assign(form, await settingsApi.getSettings())
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function save() {
  saving.value = true
  try {
    const updated = await settingsApi.updateSettings({ ...form })
    Object.assign(form, updated)
    ElMessage.success('设置已保存')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="title-row">
      <h1>系统设置</h1>
      <RefreshButton :loading="loading" @refresh="load" />
    </div>

    <el-form label-position="top" class="settings-form">
      <section class="panel">
        <h2>开放使用</h2>
        <el-form-item>
          <div class="switch-row">
            <el-switch v-model="form.open_access" />
            <span>
              {{
                form.open_access
                  ? '已开启：访客可直接查询，匿名 API 调用也放行'
                  : '已关闭：查询需要登录或有效 Token'
              }}
            </span>
          </div>
        </el-form-item>
        <el-form-item>
          <div class="switch-row">
            <el-switch v-model="form.allow_registration" />
            <span>{{ form.allow_registration ? '允许用户自助注册' : '已关闭自助注册' }}</span>
          </div>
        </el-form-item>
      </section>

      <section class="panel">
        <h2>限流设置</h2>
        <el-form-item label="Token 默认每日调用上限">
          <el-input-number v-model="form.token_default_daily_limit" :min="1" style="width: 220px" />
        </el-form-item>
        <el-form-item label="匿名访问单 IP 每分钟请求上限">
          <el-input-number
            v-model="form.anonymous_ip_rate_limit_per_min"
            :min="1"
            style="width: 220px"
          />
        </el-form-item>
        <el-form-item label="登录用户单 IP 每分钟请求上限">
          <el-input-number
            v-model="form.user_ip_rate_limit_per_min"
            :min="1"
            style="width: 220px"
          />
        </el-form-item>
      </section>

      <section class="panel">
        <h2>生词本</h2>
        <el-form-item>
          <el-checkbox v-model="vocabUnlimited">不限容量</el-checkbox>
        </el-form-item>
        <el-form-item v-if="!vocabUnlimited" label="单用户/单 Token 生词本容量上限">
          <el-input-number v-model="form.vocab_max_items_per_owner" :min="1" style="width: 220px" />
        </el-form-item>
      </section>

      <section class="panel">
        <h2>站点信息</h2>
        <el-form-item label="站点名称">
          <el-input v-model="form.site_name" style="width: 320px" />
        </el-form-item>
        <el-form-item label="搜索提示语（登录用户在首页搜索框下方看到，限 100 字以内）">
          <el-input
            v-model="form.search_hint_text"
            maxlength="100"
            show-word-limit
            style="width: 320px"
          />
        </el-form-item>
      </section>

      <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
    </el-form>
  </div>
</template>

<style scoped>
.page {
  max-width: 720px;
  margin: var(--space-6) auto;
  padding: 0 var(--space-4);
}

.title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
}

h1 {
  font-size: var(--text-xl);
  color: var(--color-text-primary);
  margin: 0;
}

.panel {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-5);
  margin-bottom: var(--space-4);
}

.panel h2 {
  font-size: var(--text-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-4);
}

.switch-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.hint {
  margin: var(--space-3) 0 0;
  font-size: var(--text-xs);
  line-height: var(--leading-body);
  color: var(--color-text-tertiary);
}

.hint code {
  font-family: var(--font-family-mono);
  color: var(--color-text-secondary);
}

.intro {
  margin: 0 0 var(--space-4);
  line-height: var(--leading-body);
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.install-guide {
  margin-top: var(--space-4);
  border-top: 1px solid var(--color-border);
}

.step {
  margin: 0 0 var(--space-2);
  font-size: var(--text-xs);
  line-height: var(--leading-body);
  color: var(--color-text-secondary);
}

.code {
  margin: 0 0 var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-bg-base);
  color: var(--color-text-secondary);
  font-family: var(--font-family-mono);
  font-size: var(--text-xs);
  line-height: var(--leading-body);
  overflow-x: auto;
  white-space: pre;
}
</style>
