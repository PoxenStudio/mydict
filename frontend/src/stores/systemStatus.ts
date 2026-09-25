import { defineStore } from 'pinia'
import { getSystemStatus } from '../api/system'
import { onMaintenance } from '../api/request'
import type { SystemStatus } from '../types/system'

const BLOCKING_INTERVAL_MS = 3000
const IDLE_INTERVAL_MS = 60000

let timer: ReturnType<typeof setTimeout> | undefined

export const useSystemStatusStore = defineStore('systemStatus', {
  state: () => ({
    status: null as SystemStatus | null,
    // 本地收到状态的时刻，维护页据此在两次轮询之间自行累加耗时
    receivedAt: 0,
    started: false,
  }),
  getters: {
    blocking: (state) => state.status?.blocking ?? false,
    busyNotice: (state) => state.status?.busy_notice ?? null,
  },
  actions: {
    start() {
      if (this.started) return
      this.started = true
      onMaintenance(() => this.refresh())
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) this.refresh()
      })
      this.refresh()
    },
    async refresh() {
      clearTimeout(timer)
      const wasBlocking = this.blocking
      try {
        this.status = await getSystemStatus()
        this.receivedAt = Date.now()
      } catch {
        // 服务重启的间隙取不到状态：保持上一次的结论，下一轮再试
      }
      // 维护期间页面上的数据都没加载成功，恢复后整页刷新比逐个重试更可靠
      if (wasBlocking && !this.blocking) {
        window.location.reload()
        return
      }
      if (document.hidden && !this.blocking) return
      timer = setTimeout(
        () => this.refresh(),
        this.blocking ? BLOCKING_INTERVAL_MS : IDLE_INTERVAL_MS,
      )
    },
  },
})
