import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { Interaction, LeadDetail, LeadListResponse, Meta } from './types'

export interface LeadFilters {
  q: string
  category: string
  is_complete: string
  page: number
  pageSize: number
}

export function useLeads(filters: LeadFilters) {
  return useQuery({
    queryKey: ['leads', filters],
    queryFn: () =>
      api<LeadListResponse>('leads', {
        query: {
          q: filters.q,
          category: filters.category,
          is_complete: filters.is_complete,
          page: String(filters.page),
          pageSize: String(filters.pageSize),
        },
      }),
    refetchInterval: 60_000,
    placeholderData: (prev) => prev,
  })
}

export function useLead(leadId: string) {
  return useQuery({
    queryKey: ['lead', leadId],
    queryFn: () => api<LeadDetail>(`leads/${encodeURIComponent(leadId)}`),
    enabled: !!leadId,
  })
}

export function useInteractions(leadId: string) {
  return useQuery({
    queryKey: ['interactions', leadId],
    queryFn: () => api<{ items: Interaction[] }>(`leads/${encodeURIComponent(leadId)}/interactions`),
    enabled: !!leadId,
  })
}

export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => api<Meta>('meta'),
    staleTime: 5 * 60_000,
  })
}

export function useAddInteraction(leadId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<Interaction>) =>
      api<Interaction>(`leads/${encodeURIComponent(leadId)}/interactions`, {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['interactions', leadId] }),
  })
}

export function usePatchInteraction(leadId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...changes }: { id: string } & Partial<Interaction>) =>
      api<Interaction>(`leads/${encodeURIComponent(leadId)}/interactions/${id}`, {
        method: 'PATCH',
        body: changes,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['interactions', leadId] }),
  })
}
