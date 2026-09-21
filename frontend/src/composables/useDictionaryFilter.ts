import { computed, ref } from 'vue'
import { listDictionaries } from '../api/dict'
import type { PublicDictionary } from '../types/query'

// 只存在当前浏览器：词典勾选是「我这次想查哪几部」，不是「这个服务对所有人开放哪几部」。
// 后者是管理端的启用/停用，会写库、影响所有人；两者刻意分开。
const STORAGE_KEY = 'mydict-dict-filter'

function readStored(): number[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    return parsed.filter((item): item is number => typeof item === 'number')
  } catch {
    // 存的内容坏掉（手工改过、旧版本格式）时按「未设置」处理，不要因此让查询页挂掉
    return null
  }
}

function persist(ids: number[]) {
  try {
    if (!ids.length) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  } catch {
    // 隐私模式下 localStorage 可能不可写；勾选在当前会话内仍然生效
  }
}

/**
 * 查询页左侧的「检索范围」：列出全部已启用词典，勾选结果只影响本浏览器的本次检索。
 *
 * 「一个都没勾」与「全部勾上」在后端是同一个意思（不限制范围）——「限制到零部词典」
 * 不是有意义的可用状态，这一点与后端的 parse_dict_ids 保持一致。
 */
export function useDictionaryFilter() {
  const dictionaries = ref<PublicDictionary[]>([])
  const selectedIds = ref<number[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  async function load() {
    loading.value = true
    try {
      dictionaries.value = await listDictionaries()
    } catch {
      // 具体原因由响应拦截器提示；拿不到列表时按「不限制」继续，查询本身不受影响
      dictionaries.value = []
      loaded.value = true
      return
    } finally {
      loading.value = false
    }
    // 清掉已被删除/停用的 id：否则限制列表会一直堆积失效项，勾选状态也对不上
    const valid = new Set(dictionaries.value.map((item) => item.id))
    const stored = readStored()
    selectedIds.value = stored === null ? [] : stored.filter((id) => valid.has(id))
    // 全部勾上等价于不限制，统一收敛成空数组，避免「全选」和「未设置」两种表示并存
    if (selectedIds.value.length === dictionaries.value.length) selectedIds.value = []
    loaded.value = true
  }

  function setSelection(ids: number[]) {
    const unique = [...new Set(ids)].sort((a, b) => a - b)
    // 空集与全集都收敛成「不限制」：后端无法表达「限制到零部词典」（parse_dict_ids 对空值
    // 返回 None），把它当成限制反而会出现「勾光了却查出全部」的矛盾状态。界面上这一栏会
    // 立刻显示回全部勾选 + 未限制提示，用户看得到发生了什么。
    if (unique.length === 0 || unique.length === dictionaries.value.length) {
      selectedIds.value = []
    } else {
      selectedIds.value = unique
    }
    persist(selectedIds.value)
  }

  function toggle(id: number) {
    const current = new Set(selectedIds.value.length ? selectedIds.value : allIds.value)
    if (current.has(id)) current.delete(id)
    else current.add(id)
    setSelection([...current])
  }

  const allIds = computed(() => dictionaries.value.map((item) => item.id))

  /** 传给查询接口的范围；undefined 表示不限制 */
  const filterIds = computed(() => (selectedIds.value.length ? selectedIds.value : undefined))

  /** 勾选态：未设置限制时视为全选 */
  const checkedIds = computed(
    () => new Set(selectedIds.value.length ? selectedIds.value : allIds.value),
  )

  const isFiltering = computed(() => selectedIds.value.length > 0)

  return {
    dictionaries,
    selectedIds,
    checkedIds,
    allIds,
    filterIds,
    isFiltering,
    loading,
    loaded,
    load,
    toggle,
    setSelection,
  }
}
