export type AssetKind = 'character' | 'environment' | 'prop'
export type ImageStatus = 'none' | 'generating' | 'ready' | 'failed'
export type EpisodeStatus =
  | 'draft' | 'analyzing' | 'review' | 'planning' | 'imaging' | 'scenes_ready' | 'rendering' | 'completed' | 'failed'

export interface Voice { id: string; label: string; gender: string; age: string }
export interface AppConfig {
  providers: { text: string; image: string; voice: string }
  placeholder_mode: boolean
  ffmpeg: boolean
  voices: Voice[]
  aspect_ratios: string[]
}

export interface Series {
  id: number; title: string; premise: string; art_style: string; aspect_ratio: string; narrator_voice: string
  created_at: string; episode_count?: number
  asset_counts?: { total: number; approved: number; pending_review: number }
}

export interface Asset {
  id: number; series_id: number; kind: AssetKind; name: string; description: string; voice_id: string | null
  status: string; approved: boolean; image_url: string | null; image_status: ImageStatus
  last_error: string | null; correction_pending: boolean
}

export interface Ref { id: number; name: string }
export interface Scene {
  id: number; episode_id: number; number: number; narration_text: string; visual_prompt: string
  speaker: Ref | null; environment: Ref | null; characters: Ref[]; props: Ref[]
  image_url: string | null; image_status: ImageStatus; last_error: string | null; correction_pending: boolean
  audio_duration: number | null; has_audio: boolean; has_clip: boolean
}

export interface Actions {
  edit_script: boolean; analyze: boolean; produce: boolean; render: boolean; retry: boolean; reset: boolean; edit_scenes: boolean
}

export interface Episode {
  id: number; series_id: number; aspect_ratio: string; number: number; title: string; status: EpisodeStatus
  failed_stage: string | null; error: string | null; progress_note: string | null
  video_url: string | null; duration_seconds: number | null
  asset_total: number; asset_approved: number; blocking_assets: string[]
  scene_count: number; actions: Actions; created_at: string; updated_at: string
  script?: string; assets?: Asset[]; scenes?: Scene[]
}
