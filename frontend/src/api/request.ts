import axios, { type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { clearTokens, getAccessToken } from '../utils/authStorage'

const request = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

request.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const isAdminApi = config.url?.startsWith('/admin')
  const token = getAccessToken(isAdminApi ? 'admin' : 'user')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    const isAdminApi = (error.config?.url as string | undefined)?.startsWith('/admin')
    const message = error.response?.data?.message

    if (status === 401) {
      clearTokens(isAdminApi ? 'admin' : 'user')
      router.push(isAdminApi ? '/admin/login' : '/login')
    } else if (status === 403) {
      ElMessage.warning(message ?? '无权限执行该操作')
    } else if (status === 429) {
      ElMessage.warning('操作过于频繁，请稍后再试')
    } else if (message) {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  },
)

export default request
