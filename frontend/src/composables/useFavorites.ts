import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { addVocab, deleteVocab, listVocab } from '../api/vocab'
import { useUserAuthStore } from '../stores/userAuth'

/** 查询结果卡片、历史记录等多处复用的"收藏/取消收藏"状态与逻辑。 */
export function useFavorites() {
  const router = useRouter()
  const authStore = useUserAuthStore()

  // word(小写) -> 生词本条目 id，用于收藏态展示与取消收藏
  const favoriteMap = ref<Map<string, number>>(new Map())
  const favoriteLoading = ref<Set<string>>(new Set())

  async function loadFavorites() {
    if (!authStore.isLoggedIn) return
    try {
      const resp = await listVocab(undefined, 1, 100)
      const map = new Map<string, number>()
      for (const item of resp.items) map.set(item.word.toLowerCase(), item.id)
      favoriteMap.value = map
    } catch {
      // 生词本预加载失败不影响主流程
    }
  }

  function isFavorited(word: string) {
    return favoriteMap.value.has(word.toLowerCase())
  }

  async function toggleFavorite(word: string, dictionaryId: number | null | undefined) {
    if (!authStore.isLoggedIn) {
      ElMessage.warning('登录后才能收藏生词')
      router.push('/login')
      return
    }
    const key = word.toLowerCase()
    favoriteLoading.value.add(key)
    try {
      if (isFavorited(word)) {
        const id = favoriteMap.value.get(key)!
        await deleteVocab(id)
        favoriteMap.value.delete(key)
      } else {
        const item = await addVocab(word, dictionaryId ?? undefined)
        favoriteMap.value.set(key, item.id)
      }
      favoriteMap.value = new Map(favoriteMap.value)
    } catch {
      // 错误已由响应拦截器统一提示
    } finally {
      favoriteLoading.value.delete(key)
    }
  }

  return { favoriteMap, favoriteLoading, loadFavorites, isFavorited, toggleFavorite }
}
