const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

// --- Types (alignés sur api/schemas.py) ---

export interface LLMConfig {
  provider: string
  model: string
  api_key?: string
  api_base?: string
  thinking?: 'off' | 'low' | 'medium' | 'high'
}

export interface ProjectCreateRequest {
  name: string
  source_text: string
  llm: LLMConfig
  target_chapter_count?: number
  writing_style?: string
  tone_keywords?: string[]
  min_validation_score?: number
  max_revision_attempts?: number
}

export interface Project {
  id: string
  name: string
  created_at: string
  status: string
  chapter_count: number
  chapters_done: number
  // ProjectDetail fields
  source_text?: string
  llm_provider?: string
  llm_model?: string
  llm_thinking?: string | null
  target_chapter_count?: number | null
  writing_style?: string | null
  tone_keywords?: string[]
}

export interface PipelineStatus {
  project_id: string
  status: 'idle' | 'running' | 'completed' | 'error' | 'stopping'
  current_agent: string | null
  error: string | null
  started_at: string | null
  completed_at: string | null
  chapters: unknown[]
}

export interface ChapterResponse {
  number: number
  title: string | null
  state: string
  content: string | null
  score: number | null
  revision_count: number
}

export interface LorebookResponse {
  characters: Record<string, string>
  places: Record<string, string>
  lore: Record<string, string>
}

// --- API calls ---

export const api = {
  projects: {
    list: () => request<Project[]>('/projects'),
    get: (id: string) => request<Project>(`/projects/${id}`),
    create: (data: ProjectCreateRequest) =>
      request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/projects/${id}`, { method: 'DELETE' }),
  },

  pipeline: {
    run: (id: string) => request<PipelineStatus>(`/projects/${id}/run`, { method: 'POST' }),
    stop: (id: string) => request<PipelineStatus>(`/projects/${id}/stop`, { method: 'POST' }),
    status: (id: string) => request<PipelineStatus>(`/projects/${id}/status`),
  },

  content: {
    chapters: (id: string) => request<ChapterResponse[]>(`/projects/${id}/chapters`),
    chapter: (id: string, num: number) => request<ChapterResponse>(`/projects/${id}/chapters/${num}`),
    lorebook: (id: string) => request<LorebookResponse>(`/projects/${id}/lorebook`),
  },
}
