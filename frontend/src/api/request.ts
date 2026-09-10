import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('mydict-jwt')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 401/403/429 等统一提示逻辑将随登录态相关功能一并实现（见 Step 1）
    return Promise.reject(error)
  },
)

export default request
