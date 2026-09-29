import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { addVocab, deleteVocab, listVocab } from '../api/vocab'
import { useUserAuthStore } from '../stores/userAuth'

/**
 * 收藏态的唯一键：**同一个词在不同词典里是两条独立的生词**（词条级生词本），
 * 所以判定「已收藏」时必须带上词典 id。没有词典 id（老数据/词典已删）用空串占位。
 */
export const favoriteKey = (word: string, dictionaryId?: number | null): string =>
  `${word.trim().toLowerCase()}|${dictionaryId ?? ''}`

/** 查询结果卡片、历史记录等多处复用的"收藏/取消收藏"状态与逻辑。 */
export function useFavorites() {
  const router = useRouter()
  const authStore = useUserAuthStore()

  // favoriteKey(词+词典) -> 生词本条目 id，用于收藏态展示与取消收藏
  const favoriteMap = ref<Map<string, number>>(new Map())
  const favoriteLoading = ref<Set<string>>(new Set())

  async function loadFavorites() {
    if (!authStore.isLoggedIn) return
    try {
      const resp = await listVocab(undefined, 1, 100)
      const map = new Map<string, number>()
      for (const item of resp.items) map.set(favoriteKey(item.word, item.dictionary_id), item.id)
      favoriteMap.value = map
    } catch {
      // 生词本预加载失败不影响主流程
    }
  }

  function isFavorited(word: string, dictionaryId?: number | null) {
    return favoriteMap.value.has(favoriteKey(word, dictionaryId))
  }

  async function toggleFavorite(word: string, dictionaryId: number | null | undefined) {
    if (!authStore.isLoggedIn) {
      ElMessage.warning('登录后才能收藏生词')
      router.push('/login')
      return
    }
    const key = favoriteKey(word, dictionaryId)
    favoriteLoading.value.add(key)
    try {
      if (isFavorited(word, dictionaryId)) {
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
