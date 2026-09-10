import request from './request'
import type { QueryResponse } from '../types/query'

export function searchWord(word: string) {
  return request.get<never, QueryResponse>('/dict/search', { params: { word } })
}
