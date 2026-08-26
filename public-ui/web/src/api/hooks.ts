import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  Alert,
  Criteria,
  LeadDetail,
  LeadListResponse,
  Meta,
  Note,
  PreviewResult,
  SavedEntry,
  WorkspaceResponse,
} from './types'

export interface LeadFilters {
  q: string
  category: string
  city: string
  hoa: string
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
          city: filters.city,
          hoa: filters.hoa,
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

export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => api<Meta>('meta'),
    staleTime: 5 * 60_000,
  })
}

export function useNotes(leadId: string) {
  return useQuery({
    queryKey: ['notes', leadId],
    queryFn: () => api<{ items: Note[] }>(`leads/${encodeURIComponent(leadId)}/notes`),
    enabled: !!leadId,
  })
}

export function useAddNote(leadId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: string) =>
      api<Note>(`leads/${encodeURIComponent(leadId)}/notes`, { method: 'POST', body: { body } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notes', leadId] })
      qc.invalidateQueries({ queryKey: ['workspace'] })
    },
  })
}

export function useUpdateNote(leadId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) =>
      api<Note>(`leads/${encodeURIComponent(leadId)}/notes/${id}`, {
        method: 'PATCH',
        body: { body },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notes', leadId] }),
  })
}

export function useDeleteNote(leadId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api<{ ok: boolean }>(`leads/${encodeURIComponent(leadId)}/notes/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notes', leadId] })
      qc.invalidateQueries({ queryKey: ['workspace'] })
    },
  })
}

export function useWorkspace() {
  return useQuery({
    queryKey: ['workspace'],
    queryFn: () => api<WorkspaceResponse>('workspace'),
  })
}

export function useSaveWorkspace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ leadId, ...changes }: { leadId: string } & Partial<SavedEntry>) =>
      api<SavedEntry>(`workspace/${encodeURIComponent(leadId)}`, {
        method: 'PUT',
        body: changes,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workspace'] }),
  })
}

export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: () => api<{ items: Alert[] }>('alerts'),
  })
}

export function useSaveAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Alert> & { id?: string }) =>
      id
        ? api<Alert>(`alerts/${id}`, { method: 'PATCH', body })
        : api<Alert>('alerts', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useDeleteAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api<{ ok: boolean }>(`alerts/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useTestAlert() {
  return useMutation({
    mutationFn: (id: string) =>
      api<{ outcomes: Record<string, string> }>(`alerts/${id}/test`, { method: 'POST' }),
  })
}

export function usePreview() {
  return useMutation({
    mutationFn: (criteria: Criteria) =>
      api<PreviewResult>('alerts/preview', { method: 'POST', body: { criteria } }),
  })
}

export function usePushSubscriptions() {
  return useQuery({
    queryKey: ['push'],
    queryFn: () =>
      api<{ items: { id: string }[]; public_key: string }>('push'),
  })
}

export function useSavePush() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subscription: PushSubscriptionJSON) =>
      api<{ id: string }>('push', { method: 'POST', body: { subscription } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['push'] }),
  })
}

export function useUpdateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (changes: { display_name?: string; phone?: string; tz?: string }) =>
      api('auth/profile', { method: 'PATCH', body: changes }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
}
