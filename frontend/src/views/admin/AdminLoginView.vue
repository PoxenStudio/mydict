<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthCard from '../../components/AuthCard.vue'
import { useAdminAuthStore } from '../../stores/adminAuth'
import { bootstrapStatus } from '../../api/admin/auth'

const router = useRouter()
const authStore = useAdminAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

onMounted(async () => {
  const { initialized } = await bootstrapStatus()
  if (!initialized) {
    router.replace('/admin/setup')
  }
})

async function onSubmit() {
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    router.push('/admin')
  } catch {
    // 错误已由 request.ts 响应拦截器统一提示
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthCard title="管理后台登录">
    <el-form :model="form" label-position="top" @submit.prevent="onSubmit">
      <el-form-item label="用户名">
        <el-input v-model="form.username" placeholder="管理员用户名" />
      </el-form-item>
      <el-form-item label="密码">
        <el-input v-model="form.password" type="password" placeholder="密码" show-password />
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
        登录
      </el-button>
    </el-form>
    <p class="switch-link"><router-link to="/">返回首页</router-link></p>
  </AuthCard>
</template>

<style scoped>
.switch-link {
  margin: var(--space-4) 0 0;
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}
</style>
