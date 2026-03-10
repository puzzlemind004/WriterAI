import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Play, Square, Loader2, BookOpen,
  Users, MapPin, Scroll, ChevronDown, ChevronUp,
  CheckCircle, Clock, PenLine, AlertCircle, Eye,
} from 'lucide-react'
import { api, type ChapterResponse } from '../api/client'

// --- SSE hook — géré au niveau page, partage les invalidations ---

function useSSE(projectId: string, isRunning: boolean) {
  const qc = useQueryClient()
  const esRef = useRef<EventSource | null>(null)

  function connect() {
    if (esRef.current) esRef.current.close()
    const es = new EventSource(`/api/projects/${projectId}/stream`)
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        handleEvent(data)
      } catch { /* ignore malformed */ }
    }

    es.onerror = () => {
      es.close()
      esRef.current = null
    }

    function handleEvent(data: { type: string; payload?: Record<string, unknown> }) {
      switch (data.type) {
        case 'agent.started':
        case 'agent.completed':
        case 'agent.failed':
          qc.invalidateQueries({ queryKey: ['pipeline', projectId] })
          break

        case 'chapter.state_changed':
          // Invalide à chaque changement d'état, pas seulement sur validated
          qc.invalidateQueries({ queryKey: ['chapters', projectId] })
          // Si validé, invalider aussi le projet (compteur chapters_done)
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
          break

        case 'pipeline.error':
          qc.invalidateQueries({ queryKey: ['pipeline', projectId] })
          qc.invalidateQueries({ queryKey: ['chapters', projectId] })
          es.close()
          esRef.current = null
          break
      }
    }
  }

  useEffect(() => {
    if (isRunning) connect()
    return () => { esRef.current?.close() }
  }, [isRunning])

  return { connect }
}

// --- Pipeline bar ---

function PipelineBar({ projectId }: { projectId: string }) {
  const qc = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ['pipeline', projectId],
    queryFn: () => api.pipeline.status(projectId),
    // Pas de polling — SSE gère les mises à jour en temps réel
    // Seul un refetch au montage pour avoir l'état initial
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  const isRunning = status?.status === 'running' || status?.status === 'stopping'

  const { connect } = useSSE(projectId, isRunning)

  const run = useMutation({
    mutationFn: () => api.pipeline.run(projectId),
    onSuccess: (data) => {
      qc.setQueryData(['pipeline', projectId], data)
      connect() // Ouvre le SSE dès le lancement
    },
  })

  const stop = useMutation({
    mutationFn: () => api.pipeline.stop(projectId),
    onSuccess: (data) => qc.setQueryData(['pipeline', projectId], data),
  })

  if (!status) return null

  const statusConfig: Record<string, { label: string; color: string; dot: string }> = {
    idle:      { label: 'En attente',   color: 'text-slate-400', dot: 'bg-slate-600' },
    running:   { label: 'En cours…',    color: 'text-yellow-400', dot: 'bg-yellow-400 animate-pulse' },
    stopping:  { label: 'Arrêt…',       color: 'text-orange-400', dot: 'bg-orange-400 animate-pulse' },
    completed: { label: 'Terminé',      color: 'text-green-400',  dot: 'bg-green-400' },
    error:     { label: 'Erreur',        color: 'text-red-400',   dot: 'bg-red-400' },
  }
  const cfg = statusConfig[status.status] ?? statusConfig.idle

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-6">
      <div className="flex items-center gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
            <span className={`text-sm font-medium ${cfg.color}`}>{cfg.label}</span>
            {isRunning && status.current_agent && (
              <span className="text-xs text-slate-500 truncate">
                — <Loader2 className="inline w-3 h-3 animate-spin mr-1" />{status.current_agent}
              </span>
            )}
          </div>
          {status.status === 'error' && status.error && (
            <p className="text-xs text-red-400 mt-1 truncate">{status.error}</p>
          )}
        </div>

        {isRunning ? (
          <button
            onClick={() => stop.mutate()}
            disabled={stop.isPending || status.status === 'stopping'}
            className="flex items-center gap-2 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex-shrink-0"
          >
            <Square className="w-4 h-4" />
            Arrêter
          </button>
        ) : (
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex-shrink-0"
          >
            {run.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {status.status === 'completed' ? 'Relancer' : 'Lancer'}
          </button>
        )}
      </div>
    </div>
  )
}

// --- Chapter item ---

const STATE_CONFIG: Record<string, { label: string; color: string; Icon: React.FC<{ className?: string }> }> = {
  planned:           { label: 'Planifié',    color: 'text-slate-400 bg-slate-800',          Icon: Clock },
  writing:           { label: 'Rédaction…',  color: 'text-yellow-400 bg-yellow-900/30',     Icon: PenLine },
  in_review:         { label: 'Révision…',   color: 'text-blue-400 bg-blue-900/30',         Icon: Eye },
  revision_requested:{ label: 'Correction',  color: 'text-orange-400 bg-orange-900/30',     Icon: AlertCircle },
  validated:         { label: 'Rédigé',      color: 'text-green-400 bg-green-900/30',       Icon: CheckCircle },
  error:             { label: 'Erreur',      color: 'text-red-400 bg-red-900/30',           Icon: AlertCircle },
}

function ChapterItem({ chapter }: { chapter: ChapterResponse }) {
  const [open, setOpen] = useState(false)
  const cfg = STATE_CONFIG[chapter.state] ?? STATE_CONFIG.planned
  const hasContent = !!chapter.content

  return (
    <div className="border border-slate-800 rounded-lg overflow-hidden">
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
          {chapter.score != null && (
            <span className="text-xs text-slate-600 flex-shrink-0">{chapter.score.toFixed(1)}/10</span>
          )}
        </div>
        {hasContent && (
          open
            ? <ChevronUp className="w-4 h-4 text-slate-600 flex-shrink-0" />
            : <ChevronDown className="w-4 h-4 text-slate-600 flex-shrink-0" />
        )}
      </button>

      {open && hasContent && (
        <div className="border-t border-slate-800 px-6 py-5">
          {chapter.revision_count > 0 && (
            <p className="text-xs text-slate-600 mb-3">
              {chapter.revision_count} révision{chapter.revision_count > 1 ? 's' : ''}
            </p>
          )}
          <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-serif">
            {chapter.content}
          </div>
        </div>
      )}
    </div>
  )
}

// --- Lorebook ---

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

// --- Main page ---

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

  return (
    <div className="min-h-screen bg-slate-950 p-8">
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
            <div className="flex items-center gap-3 mt-1 text-sm text-slate-500">
              {project.writing_style && <span>{project.writing_style}</span>}
              {project.llm_model && (
                <>
                  {project.writing_style && <span>·</span>}
                  <span>{project.llm_model}</span>
                  {project.llm_thinking && (
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
            </div>
          </div>
        )}

        {id && <PipelineBar projectId={id} />}

        {/* Chapters */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Chapitres</h2>
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
  )
}
