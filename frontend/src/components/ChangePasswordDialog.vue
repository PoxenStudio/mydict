<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { changePassword } from '../api/auth'

const visible = defineModel<boolean>('visible', { required: true })

const loading = ref(false)
const form = reactive({ oldPassword: '', newPassword: '', confirm: '' })

function resetForm() {
  form.oldPassword = ''
  form.newPassword = ''
  form.confirm = ''
}

async function submit() {
  if (form.newPassword.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (form.newPassword !== form.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  loading.value = true
  try {
    await changePassword(form.oldPassword, form.newPassword)
    ElMessage.success('密码已修改')
    visible.value = false
    resetForm()
  } catch {
    // 错误已由 request.ts 响应拦截器统一提示
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="修改密码" width="380px" @close="resetForm">
    <el-form :model="form" label-position="top" @submit.prevent="submit">
      <el-form-item label="原密码">
        <el-input v-model="form.oldPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="form.newPassword" type="password" placeholder="至少 8 位" show-password />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="form.confirm" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>
