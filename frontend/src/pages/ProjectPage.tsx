import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Play, Square, Loader2, BookOpen,
  Users, MapPin, Scroll, ChevronDown, ChevronUp,
  CheckCircle, Clock, PenLine, AlertCircle, Eye,
  Download, FileText, Star, RotateCcw, Wifi, WifiOff,
} from 'lucide-react'
import { api, type ChapterResponse } from '../api/client'
import AppLayout from '../components/AppLayout'

// ─────────────────────────────────────────────
//  SSE hook — reconnexion automatique (point 8)
// ─────────────────────────────────────────────

const SSE_MAX_RETRIES = 10
const SSE_BASE_DELAY = 2000   // ms, doublement exponentiel plafonné à 30 s

function useSSE(projectId: string, isRunning: boolean) {
  const qc = useQueryClient()
  const esRef = useRef<EventSource | null>(null)
  const retryRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [sseState, setSseState] = useState<'connected' | 'disconnected' | 'idle'>('idle')

  const connect = useCallback(() => {
    if (esRef.current) esRef.current.close()
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current)

    const es = new EventSource(`/api/projects/${projectId}/stream`)
    esRef.current = es
    setSseState('connected')

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        handleEvent(data)
      } catch { /* ignore malformed */ }
    }

    es.onerror = () => {
      es.close()
      esRef.current = null
      setSseState('disconnected')

      // Reconnexion exponentielle si le pipeline tourne encore
      if (retryRef.current < SSE_MAX_RETRIES) {
        const delay = Math.min(SSE_BASE_DELAY * 2 ** retryRef.current, 30000)
        retryRef.current += 1
        retryTimerRef.current = setTimeout(() => {
          qc.invalidateQueries({ queryKey: ['pipeline', projectId] })
          connect()
        }, delay)
      }
    }

    function handleEvent(data: { type: string; payload?: Record<string, unknown> }) {
      switch (data.type) {
        case 'agent.started':
        case 'agent.completed':
        case 'agent.failed':
          qc.invalidateQueries({ queryKey: ['pipeline', projectId] })
          break

        case 'chapter.state_changed':
          qc.invalidateQueries({ queryKey: ['chapters', projectId] })
          if (data.payload?.new_state === 'validated') {
            qc.invalidateQueries({ queryKey: ['project', projectId] })
            qc.invalidateQueries({ queryKey: ['projects'] })
          }
          break

        case 'lorebook.updated':
          qc.invalidateQueries({ queryKey: ['lorebook', projectId] })
          break

        case 'pipeline.completed':
          qc.invalidateQueries({ queryKey: ['pipeline', projectId] })
          qc.invalidateQueries({ queryKey: ['chapters', projectId] })
          qc.invalidateQueries({ queryKey: ['lorebook', projectId] })
          qc.invalidateQueries({ queryKey: ['project', projectId] })
          qc.invalidateQueries({ queryKey: ['projects'] })
          es.close()
          esRef.current = null
          setSseState('idle')
          retryRef.current = 0
          break

        case 'pipeline.error':
          qc.invalidateQueries({ queryKey: ['pipeline', projectId] })
          qc.invalidateQueries({ queryKey: ['chapters', projectId] })
          es.close()
          esRef.current = null
          setSseState('idle')
          retryRef.current = 0
          break
      }
    }
  }, [projectId, qc])

  // Lance le SSE automatiquement si le pipeline tourne au montage
  useEffect(() => {
    if (isRunning) {
      retryRef.current = 0
      connect()
    }
    return () => {
      esRef.current?.close()
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
    }
  }, [isRunning, connect])

  // Réinitialise le compteur de retries quand on relance manuellement
  const connectFresh = useCallback(() => {
    retryRef.current = 0
    connect()
  }, [connect])

  return { connect: connectFresh, sseState }
}

// ─────────────────────────────────────────────
//  Pipeline bar (point 7 : erreur visible)
// ─────────────────────────────────────────────

function PipelineBar({ projectId }: { projectId: string }) {
  const qc = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ['pipeline', projectId],
    queryFn: () => api.pipeline.status(projectId),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  const isRunning = status?.status === 'running' || status?.status === 'stopping'

  const { connect, sseState } = useSSE(projectId, isRunning)

  const run = useMutation({
    mutationFn: () => api.pipeline.run(projectId),
    onSuccess: (data) => {
      qc.setQueryData(['pipeline', projectId], data)
      connect()
    },
  })

  const stop = useMutation({
    mutationFn: () => api.pipeline.stop(projectId),
    onSuccess: (data) => qc.setQueryData(['pipeline', projectId], data),
  })

  if (!status) return null

  const statusConfig: Record<string, { label: string; color: string; dot: string }> = {
    idle:      { label: 'En attente',   color: 'text-slate-400',  dot: 'bg-slate-600' },
    running:   { label: 'En cours…',    color: 'text-yellow-400', dot: 'bg-yellow-400 animate-pulse' },
    stopping:  { label: 'Arrêt…',       color: 'text-orange-400', dot: 'bg-orange-400 animate-pulse' },
    completed: { label: 'Terminé',      color: 'text-green-400',  dot: 'bg-green-400' },
    error:     { label: 'Erreur',       color: 'text-red-400',    dot: 'bg-red-400' },
  }
  const cfg = statusConfig[status.status] ?? statusConfig.idle

  return (
    <div className={`border rounded-xl p-4 mb-6 ${
      status.status === 'error'
        ? 'bg-red-950/30 border-red-800'
        : 'bg-slate-900 border-slate-800'
    }`}>
      <div className="flex items-center gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
            <span className={`text-sm font-medium ${cfg.color}`}>{cfg.label}</span>

            {isRunning && status.current_agent && (
              <span className="text-xs text-slate-500 truncate">
                — <Loader2 className="inline w-3 h-3 animate-spin mr-1" />{status.current_agent}
              </span>
            )}

            {/* Indicateur SSE (point 8) */}
            {isRunning && (
              <span className="ml-auto text-xs flex items-center gap-1" title={sseState === 'connected' ? 'Connexion temps réel active' : 'Reconnexion en cours…'}>
                {sseState === 'connected'
                  ? <Wifi className="w-3 h-3 text-green-600" />
                  : <WifiOff className="w-3 h-3 text-slate-600 animate-pulse" />
                }
              </span>
            )}
          </div>

          {/* Message d'erreur détaillé (point 7) */}
          {status.status === 'error' && status.error && (
            <div className="mt-2 text-xs text-red-300 bg-red-900/30 border border-red-800/50 rounded-lg px-3 py-2 break-words">
              <span className="font-medium">Erreur : </span>{status.error}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isRunning ? (
            <button
              onClick={() => stop.mutate()}
              disabled={stop.isPending || status.status === 'stopping'}
              className="flex items-center gap-2 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Square className="w-4 h-4" />
              Arrêter
            </button>
          ) : (
            <button
              onClick={() => run.mutate()}
              disabled={run.isPending}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              {run.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {status.status === 'error' ? 'Relancer' : status.status === 'completed' ? 'Relancer' : 'Lancer'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
//  Chapter item (point 5 : détails révisions)
// ─────────────────────────────────────────────

const STATE_CONFIG: Record<string, { label: string; color: string; Icon: React.FC<{ className?: string }> }> = {
  planned:            { label: 'Planifié',   color: 'text-slate-400 bg-slate-800',        Icon: Clock },
  writing:            { label: 'Rédaction…', color: 'text-yellow-400 bg-yellow-900/30',   Icon: PenLine },
  in_review:          { label: 'Révision…',  color: 'text-blue-400 bg-blue-900/30',       Icon: Eye },
  revision_requested: { label: 'Correction', color: 'text-orange-400 bg-orange-900/30',   Icon: AlertCircle },
  validated:          { label: 'Rédigé',     color: 'text-green-400 bg-green-900/30',     Icon: CheckCircle },
  error:              { label: 'Erreur',     color: 'text-red-400 bg-red-900/30',         Icon: AlertCircle },
}

function ScoreBar({ score }: { score: number }) {
  const pct = (score / 10) * 100
  const color = score >= 8 ? 'bg-green-500' : score >= 6 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-500 w-10 text-right">{score.toFixed(1)}/10</span>
    </div>
  )
}

function ChapterItem({ chapter }: { chapter: ChapterResponse }) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'content' | 'details'>('content')
  const cfg = STATE_CONFIG[chapter.state] ?? STATE_CONFIG.planned
  const hasContent = !!chapter.content

  // Retire la première ligne si c'est le titre markdown (# ...) et découpe en scènes sur ---
  const scenes = (chapter.content ?? '')
    .replace(/^#[^\n]*\n?/, '')   // retire le titre
    .split(/\n---\n/)
    .map(s => s.trim())
    .filter(Boolean)

  return (
    <div className="border border-slate-800 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        className="w-full flex items-center justify-between p-4 hover:bg-slate-800/50 transition-colors text-left"
        onClick={() => hasContent && setOpen(o => !o)}
        style={{ cursor: hasContent ? 'pointer' : 'default' }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-xs font-mono text-slate-600 w-6 flex-shrink-0">
            {chapter.number}
          </span>
          <span className="text-sm font-medium text-white truncate">
            {chapter.title ?? `Chapitre ${chapter.number}`}
          </span>
          <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${cfg.color}`}>
            <cfg.Icon className="w-3 h-3" />
            {cfg.label}
          </span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 ml-2">
          {chapter.score != null && (
            <span className="flex items-center gap-1 text-xs text-slate-500">
              <Star className="w-3 h-3 text-yellow-600" />
              {chapter.score.toFixed(1)}
            </span>
          )}
          {chapter.revision_count > 0 && (
            <span className="flex items-center gap-1 text-xs text-slate-600">
              <RotateCcw className="w-3 h-3" />
              {chapter.revision_count}
            </span>
          )}
          {hasContent && (
            open
              ? <ChevronUp className="w-4 h-4 text-slate-600" />
              : <ChevronDown className="w-4 h-4 text-slate-600" />
          )}
        </div>
      </button>

      {/* Corps déplié */}
      {open && hasContent && (
        <div className="border-t border-slate-800">
          {/* Onglets */}
          <div className="flex border-b border-slate-800">
            <button
              onClick={() => setTab('content')}
              className={`px-4 py-2 text-xs transition-colors ${tab === 'content' ? 'text-white border-b-2 border-indigo-500' : 'text-slate-500 hover:text-slate-300'}`}
            >
              Texte
            </button>
            <button
              onClick={() => setTab('details')}
              className={`px-4 py-2 text-xs transition-colors ${tab === 'details' ? 'text-white border-b-2 border-indigo-500' : 'text-slate-500 hover:text-slate-300'}`}
            >
              Détails
            </button>
          </div>

          {tab === 'content' && (
            <div className="px-6 py-5 space-y-8">
              {scenes.map((scene, i) => (
                <div key={i}>
                  {scenes.length > 1 && (
                    <p className="text-xs text-slate-600 mb-3 font-mono">— Scène {i + 1} —</p>
                  )}
                  <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-serif">
                    {scene}
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === 'details' && (
            <div className="px-6 py-5 space-y-5">
              {/* Stats */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-slate-800/50 rounded-lg p-3 text-center">
                  <p className="text-lg font-bold text-white">{chapter.content?.split(/\s+/).filter(Boolean).length ?? 0}</p>
                  <p className="text-xs text-slate-500">mots</p>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3 text-center">
                  <p className="text-lg font-bold text-white">{chapter.revision_count}</p>
                  <p className="text-xs text-slate-500">révision{chapter.revision_count !== 1 ? 's' : ''}</p>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3 text-center">
                  <p className={`text-lg font-bold ${STATE_CONFIG[chapter.state]?.color.split(' ')[0] ?? 'text-slate-400'}`}>
                    {STATE_CONFIG[chapter.state]?.label ?? chapter.state}
                  </p>
                  <p className="text-xs text-slate-500">état</p>
                </div>
              </div>

              {/* Score critique */}
              {chapter.score != null && (
                <div>
                  <p className="text-xs text-slate-500 mb-2">Note du critique</p>
                  <ScoreBar score={chapter.score} />
                </div>
              )}

              {/* Commentaires du critique */}
              {(chapter.critic_comments?.length ?? 0) > 0 && (
                <div>
                  <p className="text-xs text-slate-500 mb-2">Retours du critique</p>
                  <ul className="space-y-1">
                    {(chapter.critic_comments ?? []).map((c, i) => (
                      <li key={i} className="flex gap-2 text-xs text-slate-400">
                        <span className="text-slate-600 flex-shrink-0">—</span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Brief / fiche narrative */}
              {chapter.brief && (
                <div>
                  <p className="text-xs text-slate-500 mb-2">Fiche narrative</p>
                  <div className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-3 text-xs text-slate-400 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                    {chapter.brief}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
//  Export (point 4)
// ─────────────────────────────────────────────

function ExportButton({ projectName, chapters }: { projectName: string; chapters: ChapterResponse[] }) {
  const [open, setOpen] = useState(false)
  const validatedChapters = chapters.filter(c => c.state === 'validated' && c.content)

  if (!validatedChapters.length) return null

  function buildMarkdown(): string {
    const lines: string[] = [`# ${projectName}`, '']
    for (const ch of validatedChapters) {
      lines.push(ch.content!)
      lines.push('')
      lines.push('---')
      lines.push('')
    }
    return lines.join('\n')
  }

  function downloadMarkdown() {
    const md = buildMarkdown()
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${projectName.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.md`
    a.click()
    URL.revokeObjectURL(url)
    setOpen(false)
  }

  function downloadTxt() {
    const md = buildMarkdown()
    const blob = new Blob([md], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${projectName.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.txt`
    a.click()
    URL.revokeObjectURL(url)
    setOpen(false)
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 text-sm text-slate-400 hover:text-white border border-slate-700 hover:border-slate-500 px-3 py-1.5 rounded-lg transition-colors"
      >
        <Download className="w-4 h-4" />
        Exporter ({validatedChapters.length} ch.)
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 z-20 bg-slate-800 border border-slate-700 rounded-lg shadow-xl w-44 overflow-hidden">
            <button
              onClick={downloadMarkdown}
              className="w-full flex items-center gap-2 px-4 py-3 text-sm text-slate-300 hover:bg-slate-700 transition-colors text-left"
            >
              <FileText className="w-4 h-4 text-slate-500" />
              Markdown (.md)
            </button>
            <button
              onClick={downloadTxt}
              className="w-full flex items-center gap-2 px-4 py-3 text-sm text-slate-300 hover:bg-slate-700 transition-colors text-left"
            >
              <FileText className="w-4 h-4 text-slate-500" />
              Texte brut (.txt)
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
//  Lorebook
// ─────────────────────────────────────────────

function LorebookSection({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<'characters' | 'places' | 'lore'>('characters')
  const [selected, setSelected] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['lorebook', projectId],
    queryFn: () => api.content.lorebook(projectId),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  if (!data) return null

  const tabs = [
    { key: 'characters' as const, label: 'Personnages', icon: Users },
    { key: 'places'     as const, label: 'Lieux',       icon: MapPin },
    { key: 'lore'       as const, label: 'Lore',        icon: Scroll },
  ]
  const visibleTabs = tabs.filter(t => Object.keys(data[t.key]).length > 0)
  if (!visibleTabs.length) return null

  const current = data[tab] ?? {}
  const keys = Object.keys(current)

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold text-white mb-4">Lorebook</h2>
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="flex border-b border-slate-800">
          {visibleTabs.map(t => (
            <button
              key={t.key}
              onClick={() => { setTab(t.key); setSelected(null) }}
              className={`flex items-center gap-2 px-4 py-3 text-sm transition-colors ${
                tab === t.key
                  ? 'text-white border-b-2 border-indigo-500'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
              <span className="text-xs text-slate-600">({Object.keys(data[t.key]).length})</span>
            </button>
          ))}
        </div>
        <div className="flex min-h-48">
          <div className="w-48 border-r border-slate-800 py-2 flex-shrink-0">
            {keys.map(k => (
              <button
                key={k}
                onClick={() => setSelected(k === selected ? null : k)}
                className={`w-full text-left px-4 py-2 text-sm transition-colors truncate ${
                  selected === k
                    ? 'bg-indigo-900/40 text-indigo-300'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                {k}
              </button>
            ))}
          </div>
          <div className="flex-1 p-4 overflow-auto">
            {selected && current[selected] ? (
              <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                {current[selected]}
              </div>
            ) : (
              <p className="text-sm text-slate-600 italic">Sélectionnez une entrée</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
//  Page principale
// ─────────────────────────────────────────────

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: project, error: projectError } = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.projects.get(id!),
    enabled: !!id,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  const { data: chapters, isLoading: chaptersLoading, error: chaptersError } = useQuery({
    queryKey: ['chapters', id],
    queryFn: () => api.content.chapters(id!),
    enabled: !!id,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  const validatedCount = chapters?.filter(c => c.state === 'validated').length ?? 0
  const totalCount = chapters?.length ?? 0
  const wordCount = chapters
    ?.filter(c => c.content)
    .reduce((sum, c) => sum + (c.content?.split(/\s+/).filter(Boolean).length ?? 0), 0) ?? 0

  return (
    <AppLayout>
    <div className="p-8">
      <div className="max-w-3xl mx-auto">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-slate-500 hover:text-white mb-6 transition-colors text-sm"
        >
          <ArrowLeft className="w-4 h-4" />
          Projets
        </button>

        {projectError ? (
          <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 mb-6 text-red-400 text-sm">
            Impossible de charger le projet : {(projectError as Error).message}
          </div>
        ) : project && (
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-white">{project.name}</h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-slate-500 flex-wrap">
              {project.writing_style && <span>{project.writing_style}</span>}
              {project.llm_model && (
                <>
                  {project.writing_style && <span>·</span>}
                  <span>{project.llm_model}</span>
                  {project.llm_thinking && project.llm_thinking !== 'off' && (
                    <span className="text-slate-600">thinking={project.llm_thinking}</span>
                  )}
                </>
              )}
              {totalCount > 0 && (
                <>
                  <span>·</span>
                  <span>{validatedCount}/{totalCount} chapitres rédigés</span>
                </>
              )}
              {wordCount > 0 && (
                <>
                  <span>·</span>
                  <span>{wordCount.toLocaleString('fr')} mots</span>
                </>
              )}
            </div>
          </div>
        )}

        {id && <PipelineBar projectId={id} />}

        {/* Chapitres */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Chapitres</h2>
            {chapters && project && (
              <ExportButton projectName={project.name} chapters={chapters} />
            )}
          </div>

          {chaptersError ? (
            <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 text-red-400 text-sm">
              Erreur : {(chaptersError as Error).message}
            </div>
          ) : chaptersLoading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="w-6 h-6 animate-spin text-slate-600" />
            </div>
          ) : !chapters?.length ? (
            <div className="text-center py-10 text-slate-700 border border-dashed border-slate-800 rounded-xl">
              <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Aucun chapitre pour l'instant</p>
              <p className="text-xs mt-1 text-slate-800">Lancez le pipeline pour démarrer la génération</p>
            </div>
          ) : (
            <div className="space-y-2">
              {chapters.map(ch => <ChapterItem key={ch.number} chapter={ch} />)}
            </div>
          )}
        </div>

        {id && <LorebookSection projectId={id} />}
      </div>
    </div>
    </AppLayout>
  )
}
