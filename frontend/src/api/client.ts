const BASE = '/api'

// --- Token management ---

let _accessToken: string | null = localStorage.getItem('access_token')
let _onUnauthenticated: (() => void) | null = null
let _refreshPromise: Promise<boolean> | null = null

export function setOnUnauthenticated(cb: () => void) {
  _onUnauthenticated = cb
}

export function setAccessToken(token: string | null) {
  _accessToken = token
  if (token) localStorage.setItem('access_token', token)
  else localStorage.removeItem('access_token')
}

export function getAccessToken() {
  return _accessToken
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> ?? {}),
  }
  if (_accessToken) {
    headers['Authorization'] = `Bearer ${_accessToken}`
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers })

  // Auto-refresh on 401
  if (res.status === 401 && path !== '/auth/refresh' && path !== '/auth/login') {
    // Déduplique les refreshs concurrents
    if (!_refreshPromise) {
      _refreshPromise = tryRefresh().finally(() => { _refreshPromise = null })
    }
    const refreshed = await _refreshPromise
    if (refreshed) {
      headers['Authorization'] = `Bearer ${_accessToken}`
      const retry = await fetch(`${BASE}${path}`, { ...options, headers })
      if (!retry.ok) {
        const err = await retry.json().catch(() => ({ detail: retry.statusText }))
        throw new Error(err.detail ?? retry.statusText)
      }
      return retry.status === 204 ? (undefined as T) : retry.json()
    } else {
      setAccessToken(null)
      _onUnauthenticated?.()
      throw new Error('Session expirée')
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

async function tryRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
    if (!res.ok) return false
    const data = await res.json()
    setAccessToken(data.access_token)
    return true
  } catch {
    return false
  }
}

// --- Types (alignés sur api/schemas.py) ---

export interface LLMConfig {
  provider: string
  model: string
  api_key?: string
  api_key_id?: string
  api_base?: string
  thinking?: 'off' | 'low' | 'medium' | 'high'
}

export interface ApiKeyResponse {
  id: string
  label: string
  provider: string
  created_at: string
}

export interface ProjectUpdateRequest {
  name?: string
  source_text?: string
  llm?: LLMConfig
  target_chapter_count?: number
  writing_style?: string
  tone_keywords?: string[]
  min_validation_score?: number
  max_revision_attempts?: number
}

export interface ChapterVersionResponse {
  version: number
  content: string
  word_count: number
}

export interface TargetedComment {
  selected_text: string
  comment: string
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
  brief: string | null
  critic_comments: string[]
}

export interface LorebookResponse {
  characters: Record<string, string>
  places: Record<string, string>
  lore: Record<string, string>
}

export interface UserResponse {
  id: string
  email: string
  created_at: string
  is_active: boolean
}

// --- API calls ---

export const api = {
  auth: {
    register: (email: string, password: string) =>
      request<UserResponse>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }),
    login: async (email: string, password: string) => {
      const data = await request<{ access_token: string }>('/auth/login', {
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ email, password }),
      })
      setAccessToken(data.access_token)
      return data
    },
    logout: async () => {
      try {
        await fetch(`${BASE}/auth/logout`, {
          method: 'POST',
          credentials: 'include',
          headers: { Authorization: `Bearer ${_accessToken ?? ''}` },
        })
      } finally {
        setAccessToken(null)
      }
    },
    me: () => request<UserResponse>('/auth/me'),
  },

  projects: {
    list: () => request<Project[]>('/projects'),
    get: (id: string) => request<Project>(`/projects/${id}`),
    create: (data: ProjectCreateRequest) =>
      request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: ProjectUpdateRequest) =>
      request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
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
    updateChapter: (id: string, num: number, content: string, title?: string) =>
      request<ChapterResponse>(`/projects/${id}/chapters/${num}`, {
        method: 'PATCH',
        body: JSON.stringify({ content, title }),
      }),
    chapterVersions: (id: string, num: number) =>
      request<ChapterVersionResponse[]>(`/projects/${id}/chapters/${num}/versions`),
    reviseChapter: (id: string, num: number, comments: TargetedComment[]) =>
      request<ChapterResponse>(`/projects/${id}/chapters/${num}/revise`, {
        method: 'POST',
        body: JSON.stringify({ comments }),
      }),
    lorebook: (id: string) => request<LorebookResponse>(`/projects/${id}/lorebook`),
  },

  models: {
    list: (source: string) =>
      request<{ provider: string; models: string[] }>(`/models?source=${encodeURIComponent(source)}`),
  },

  account: {
    me: () => request<UserResponse>('/account/me'),
    changePassword: (current_password: string, new_password: string) =>
      request<void>('/account/password', {
        method: 'POST',
        body: JSON.stringify({ current_password, new_password }),
      }),
    listApiKeys: () => request<ApiKeyResponse[]>('/account/api-keys'),
    createApiKey: (label: string, provider: string, key_value: string) =>
      request<ApiKeyResponse>('/account/api-keys', {
        method: 'POST',
        body: JSON.stringify({ label, provider, key_value }),
      }),
    deleteApiKey: (id: string) =>
      request<void>(`/account/api-keys/${id}`, { method: 'DELETE' }),
  },
}
