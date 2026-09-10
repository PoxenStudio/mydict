<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthCard from '../components/AuthCard.vue'
import { useUserAuthStore } from '../stores/userAuth'

const router = useRouter()
const authStore = useUserAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '', email: '' })

async function onSubmit() {
  loading.value = true
  try {
    await authStore.register(form.username, form.password, form.email || undefined)
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch {
    // 错误已由 request.ts 响应拦截器统一提示
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthCard title="注册 MyDict" subtitle="注册后可使用生词本功能">
    <el-form :model="form" label-position="top" @submit.prevent="onSubmit">
      <el-form-item label="用户名">
        <el-input v-model="form.username" placeholder="3-64 位用户名" />
      </el-form-item>
      <el-form-item label="邮箱（可选）">
        <el-input v-model="form.email" placeholder="you@example.com" />
      </el-form-item>
      <el-form-item label="密码">
        <el-input v-model="form.password" type="password" placeholder="至少 8 位" show-password />
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
        注册
      </el-button>
    </el-form>
    <p class="switch-link">已有账号？<router-link to="/login">去登录</router-link></p>
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
