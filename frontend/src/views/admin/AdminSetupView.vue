<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthCard from '../../components/AuthCard.vue'
import { useAdminAuthStore } from '../../stores/adminAuth'
import { useSettingsStore } from '../../stores/settings'
import { bootstrapStatus } from '../../api/admin/auth'

const router = useRouter()
const authStore = useAdminAuthStore()
const settingsStore = useSettingsStore()
const loading = ref(false)
const form = reactive({ username: 'admin', password: '', confirm: '' })

onMounted(async () => {
  const { initialized } = await bootstrapStatus()
  if (initialized) {
    router.replace('/admin/login')
  }
})

async function onSubmit() {
  if (form.password !== form.confirm) {
    return
  }
  loading.value = true
  try {
    await authStore.setup(form.username, form.password)
    // 首页曾在未初始化时缓存过 settings，这里强制刷新一次避免跳回去又被弹回 /admin/setup
    await settingsStore.load().catch(() => undefined)
    router.push('/')
  } catch {
    // 错误已由 request.ts 响应拦截器统一提示
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthCard title="初始化管理员" subtitle="首次部署，设置管理员账号">
    <el-form :model="form" label-position="top" @submit.prevent="onSubmit">
      <el-form-item label="管理员用户名">
        <el-input v-model="form.username" placeholder="用户名" />
      </el-form-item>
      <el-form-item label="密码">
        <el-input v-model="form.password" type="password" placeholder="至少 8 位" show-password />
      </el-form-item>
      <el-form-item label="确认密码">
        <el-input v-model="form.confirm" type="password" show-password />
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
        完成初始化
      </el-button>
    </el-form>
  </AuthCard>
</template>
