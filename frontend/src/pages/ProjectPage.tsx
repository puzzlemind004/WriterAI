import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Play, Square, Loader2, BookOpen,
  Users, MapPin, Scroll, ChevronDown, ChevronUp
} from 'lucide-react'
import { api, type PipelineStatus, type ChapterResponse } from '../api/client'

// --- Pipeline status bar ---

function PipelineBar({ projectId }: { projectId: string }) {
  const qc = useQueryClient()
  const [isStreaming, setIsStreaming] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  const { data: status, refetch } = useQuery({
    queryKey: ['pipeline', projectId],
    queryFn: () => api.pipeline.status(projectId),
    refetchInterval: isStreaming ? false : 5000,
  })

  const run = useMutation({
    mutationFn: () => api.pipeline.run(projectId),
    onSuccess: () => {
      refetch()
      startStream()
    },
  })

  const stop = useMutation({
    mutationFn: () => api.pipeline.stop(projectId),
    onSuccess: () => refetch(),
  })

  function startStream() {
    if (esRef.current) esRef.current.close()
    setIsStreaming(true)
    const es = new EventSource(`/api/projects/${projectId}/stream`)
    esRef.current = es

    es.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.type === 'agent_started') {
        qc.setQueryData(['pipeline', projectId], (prev: PipelineStatus | undefined) =>
          prev ? { ...prev, current_agent: data.payload?.agent, status: 'running' } : prev
        )
      } else if (data.type === 'agent_completed') {
        qc.setQueryData(['pipeline', projectId], (prev: PipelineStatus | undefined) =>
          prev ? { ...prev, current_agent: null } : prev
        )
      } else if (data.type === 'chapter_state_changed' && data.payload?.new_state === 'validated') {
        // Un chapitre vient d'être validé : rafraîchit la liste en temps réel
        qc.invalidateQueries({ queryKey: ['chapters', projectId] })
      } else if (data.type === 'pipeline_completed') {
        es.close()
        setIsStreaming(false)
        refetch()
        qc.invalidateQueries({ queryKey: ['chapters', projectId] })
        qc.invalidateQueries({ queryKey: ['projects'] })
      } else if (data.type === 'pipeline_error') {
        es.close()
        setIsStreaming(false)
        refetch()
      }
    }

    es.onerror = () => {
      es.close()
      setIsStreaming(false)
      refetch()
    }
  }

  useEffect(() => {
    if (status?.status === 'running') startStream()
    return () => esRef.current?.close()
  }, [])

  if (!status) return null

  const isRunning = status.status === 'running'
  const isIdle = status.status === 'idle'

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-6">
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-slate-300">Pipeline</span>
            <StatusDot status={status.status} />
          </div>
          {isRunning && status.current_agent && (
            <p className="text-xs text-slate-500">
              <Loader2 className="inline w-3 h-3 animate-spin mr-1" />
              {status.current_agent}
            </p>
          )}
          {status.status === 'error' && (
            <p className="text-xs text-red-400 truncate">{status.error}</p>
          )}
          {status.status === 'completed' && (
            <p className="text-xs text-green-400">Génération terminée</p>
          )}
        </div>

        {isIdle || status.status === 'completed' || status.status === 'error' ? (
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            {run.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {status.status === 'completed' ? 'Relancer' : 'Lancer'}
          </button>
        ) : (
          <button
            onClick={() => stop.mutate()}
            className="flex items-center gap-2 bg-red-700 hover:bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Square className="w-4 h-4" />
            Arrêter
          </button>
        )}
      </div>
    </div>
  )
}

function StatusDot({ status }: { status: string }) {
  const styles: Record<string, string> = {
    idle: 'bg-slate-600',
    running: 'bg-yellow-400 animate-pulse',
    completed: 'bg-green-400',
    error: 'bg-red-400',
  }
  return <span className={`inline-block w-2 h-2 rounded-full ${styles[status] ?? styles.idle}`} />
}

// --- Chapter list ---

function ChapterItem({ chapter }: { chapter: ChapterResponse }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-slate-800 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-4 hover:bg-slate-800/50 transition-colors text-left"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-600 w-6">{chapter.number}</span>
          <span className="text-sm font-medium text-white">
            {chapter.title ?? `Chapitre ${chapter.number}`}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            chapter.state === 'validated'
              ? 'bg-green-900/50 text-green-400'
              : 'bg-slate-800 text-slate-500'
          }`}>
            {chapter.state === 'validated' ? 'Rédigé' : 'Planifié'}
          </span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-slate-600" /> : <ChevronDown className="w-4 h-4 text-slate-600" />}
      </button>
      {open && chapter.content && (
        <div className="px-4 pb-4 border-t border-slate-800">
          <div className="mt-4 prose prose-invert prose-sm max-w-none">
            <div className="text-slate-300 leading-relaxed whitespace-pre-wrap text-sm">
              {chapter.content}
            </div>
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
  })

  const tabs = [
    { key: 'characters' as const, label: 'Personnages', icon: Users },
    { key: 'places' as const, label: 'Lieux', icon: MapPin },
    { key: 'lore' as const, label: 'Lore', icon: Scroll },
  ]

  if (!data) return null
  const current = data[tab]
  const keys = Object.keys(current)
  if (!keys.length) return null

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold text-white mb-4">Lorebook</h2>
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        {/* Tabs */}
        <div className="flex border-b border-slate-800">
          {tabs.map(t => {
            const count = Object.keys(data[t.key]).length
            if (!count) return null
            return (
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
                {t.label} <span className="text-xs text-slate-600">({count})</span>
              </button>
            )
          })}
        </div>
        {/* Content */}
        <div className="flex min-h-48">
          <div className="w-48 border-r border-slate-800 py-2">
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
  })

  const { data: chapters, isLoading: chaptersLoading, error: chaptersError } = useQuery({
    queryKey: ['chapters', id],
    queryFn: () => api.content.chapters(id!),
    enabled: !!id,
  })

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
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
                  {project.llm_thinking && <span className="text-slate-600">thinking={project.llm_thinking}</span>}
                </>
              )}
            </div>
          </div>
        )}

        {/* Pipeline */}
        {id && <PipelineBar projectId={id} />}

        {/* Chapters */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Chapitres</h2>
            {chapters && chapters.length > 0 && (
              <span className="text-sm text-slate-500">
                {chapters.filter(c => c.state === 'validated').length}/{chapters.length} rédigé{chapters.length > 1 ? 's' : ''}
              </span>
            )}
          </div>

          {chaptersError ? (
            <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 text-red-400 text-sm">
              Erreur de chargement : {(chaptersError as Error).message}
            </div>
          ) : chaptersLoading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="w-6 h-6 animate-spin text-slate-600" />
            </div>
          ) : !chapters?.length ? (
            <div className="text-center py-10 text-slate-700 border border-dashed border-slate-800 rounded-xl">
              <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Aucun chapitre pour l'instant</p>
              <p className="text-xs mt-1 text-slate-800">Lancez le pipeline ci-dessus pour démarrer la génération</p>
            </div>
          ) : (
            <div className="space-y-2">
              {chapters.map(ch => <ChapterItem key={ch.number} chapter={ch} />)}
            </div>
          )}
        </div>

        {/* Lorebook */}
        {id && <LorebookSection projectId={id} />}
      </div>
    </div>
  )
}
