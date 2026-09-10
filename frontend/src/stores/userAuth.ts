import { defineStore } from 'pinia'
import * as authApi from '../api/auth'
import { clearTokens, getAccessToken, setTokens } from '../utils/authStorage'
import type { UserPublic } from '../types/auth'

export const useUserAuthStore = defineStore('userAuth', {
  state: () => ({
    profile: null as UserPublic | null,
  }),
  getters: {
    isLoggedIn: () => Boolean(getAccessToken('user')),
  },
  actions: {
    async login(username: string, password: string) {
      const tokens = await authApi.login(username, password)
      setTokens('user', tokens.access_token, tokens.refresh_token)
      await this.loadProfile()
    },
    async register(username: string, password: string, email?: string) {
      await authApi.register(username, password, email)
    },
    async loadProfile() {
      this.profile = await authApi.fetchMe()
    },
    logout() {
      clearTokens('user')
      this.profile = null
    },
  },
})
