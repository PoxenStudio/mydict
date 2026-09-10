import request from './request'
import type { PublicDictionary, QueryResponse } from '../types/query'

export function searchWord(word: string) {
  return request.get<never, QueryResponse>('/dict/search', { params: { word } })
}

export function listDictionaries() {
  return request.get<never, PublicDictionary[]>('/dict/dictionaries')
}
