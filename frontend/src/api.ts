import type { AppConfig, Asset, AssetKind, Episode, Scene, Series } from './types'

export class ApiError extends Error {
  constructor(message: string, public status: number, public detail?: unknown) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = body?.detail
    const msg = typeof d === 'string' ? d : d?.message ?? (Array.isArray(d) ? d.map((x: { msg: string }) => x.msg).join('; ') : res.statusText)
    throw new ApiError(msg, res.status, d)
  }
  return body as T
}

const json = (method: string, data?: unknown): RequestInit => ({ method, body: data === undefined ? undefined : JSON.stringify(data) })

export const api = {
  config: () => request<AppConfig>('/config'),
  previewVoice: (voice_id: string, text?: string) => request<{ url: string; provider: string }>('/voices/preview', json('POST', { voice_id, text })),

  listSeries: () => request<Series[]>('/series'),
  getSeries: (id: number) => request<Series>(`/series/${id}`),
  createSeries: (d: Partial<Series>) => request<Series>('/series', json('POST', d)),
  updateSeries: (id: number, d: Partial<Series>) => request<Series>(`/series/${id}`, json('PATCH', d)),
  deleteSeries: (id: number) => request<void>(`/series/${id}`, json('DELETE')),

  listEpisodes: (seriesId: number) => request<Episode[]>(`/series/${seriesId}/episodes`),
  createEpisode: (seriesId: number, d: { title: string; script: string }) => request<Episode>(`/series/${seriesId}/episodes`, json('POST', d)),
  listAssets: (seriesId: number) => request<Asset[]>(`/series/${seriesId}/assets`),
  createAsset: (seriesId: number, d: { kind: AssetKind; name: string; description: string; episode_id?: number }) =>
    request<Asset>(`/series/${seriesId}/assets`, json('POST', d)),

  getEpisode: (id: number) => request<Episode>(`/episodes/${id}`),
  updateEpisode: (id: number, d: { title?: string; script?: string }) => request<Episode>(`/episodes/${id}`, json('PATCH', d)),
  deleteEpisode: (id: number) => request<void>(`/episodes/${id}`, json('DELETE')),
  analyze: (id: number) => request<Episode>(`/episodes/${id}/analyze`, json('POST')),
  approveAll: (id: number) => request<{ episode: Episode; skipped_without_image: string[] }>(`/episodes/${id}/assets/approve-all`, json('POST')),
  produce: (id: number) => request<Episode>(`/episodes/${id}/produce`, json('POST')),
  render: (id: number) => request<Episode>(`/episodes/${id}/render`, json('POST')),
  retry: (id: number) => request<Episode>(`/episodes/${id}/retry`, json('POST')),
  reset: (id: number) => request<Episode>(`/episodes/${id}/reset`, json('POST')),

  updateAsset: (id: number, d: { name?: string; description?: string; voice_id?: string | null }) => request<Asset>(`/assets/${id}`, json('PATCH', d)),
  regenerateAsset: (id: number, correction?: string) => request<Asset>(`/assets/${id}/regenerate-image`, json('POST', { correction: correction || null })),
  approveAsset: (id: number) => request<Asset>(`/assets/${id}/approve`, json('POST')),
  unapproveAsset: (id: number) => request<Asset>(`/assets/${id}/unapprove`, json('POST')),
  deleteAsset: (id: number) => request<void>(`/assets/${id}`, json('DELETE')),

  updateScene: (id: number, d: { narration_text?: string; speaker_asset_id?: number | null }) => request<Scene>(`/scenes/${id}`, json('PATCH', d)),
  regenerateScene: (id: number, correction?: string) => request<Scene>(`/scenes/${id}/regenerate-image`, json('POST', { correction: correction || null })),
}
