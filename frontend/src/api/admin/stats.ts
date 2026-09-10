import request from '../request'
import type { StatRow, StatsDimension, StatsOverview, TopWordRow } from '../../types/stats'

export function getOverview() {
  return request.get<never, StatsOverview>('/admin/stats/overview')
}

export function getTopWords(startDate?: string, endDate?: string, limit = 10) {
  return request.get<never, TopWordRow[]>('/admin/stats/top-words', {
    params: { start_date: startDate, end_date: endDate, limit },
  })
}

export function getDimensionStats(dimension: StatsDimension, startDate?: string, endDate?: string) {
  return request.get<never, StatRow[]>('/admin/stats', {
    params: { dimension, start_date: startDate, end_date: endDate },
  })
}

export function exportDimensionStatsCsv(
  dimension: StatsDimension,
  startDate?: string,
  endDate?: string,
) {
  return request.get<never, Blob>('/admin/stats', {
    params: { dimension, start_date: startDate, end_date: endDate, export: 'csv' },
    responseType: 'blob',
  })
}
