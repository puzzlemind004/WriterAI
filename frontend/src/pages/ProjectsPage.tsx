import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, BookOpen, Trash2, Loader2, LogOut } from 'lucide-react'
import { api, type ProjectCreateRequest } from '../api/client'
import { useAuth } from '../auth/AuthContext'

const DEFAULT_LLM = {
  provider: 'ollama',
  model: 'gpt-oss:20b',
  api_base: 'http://localhost:11434',
  thinking: 'high' as const,
}

function NewProjectModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    name: '',
    source_text: '',
    writing_style: '',
    target_chapter_count: '',
  })

  const create = useMutation({
    mutationFn: (data: ProjectCreateRequest) => api.projects.create(data),
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${project.id}`)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload: ProjectCreateRequest = {
      name: form.name,
      source_text: form.source_text,
      llm: DEFAULT_LLM,
    }
    if (form.writing_style) payload.writing_style = form.writing_style
    if (form.target_chapter_count) payload.target_chapter_count = Number(form.target_chapter_count)
    create.mutate(payload)
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg">
        <div className="p-6">
          <h2 className="text-xl font-bold text-white mb-6">Nouveau projet</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Titre *</label>
              <input
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                placeholder="Le nom de votre roman..."
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                required
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Style d'écriture</label>
              <input
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                placeholder="Immersif, poétique, dialogues vifs..."
                value={form.writing_style}
                onChange={e => setForm(f => ({ ...f, writing_style: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                Nombre de chapitres <span className="text-slate-600">(optionnel)</span>
              </label>
              <input
                type="number"
                min={1}
                max={50}
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                placeholder="Laissez vide pour mode libre"
                value={form.target_chapter_count}
                onChange={e => setForm(f => ({ ...f, target_chapter_count: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Synopsis / Pitch *</label>
              <textarea
                rows={5}
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
                placeholder="Décrivez votre histoire, vos personnages, votre univers..."
                value={form.source_text}
                onChange={e => setForm(f => ({ ...f, source_text: e.target.value }))}
                required
                minLength={10}
              />
            </div>

            <div className="bg-slate-800/50 rounded-lg px-3 py-2 text-xs text-slate-500">
              Modèle : <span className="text-slate-400">{DEFAULT_LLM.model}</span> via Ollama · thinking={DEFAULT_LLM.thinking}
            </div>

            {create.error && (
              <p className="text-red-400 text-sm">{(create.error as Error).message}</p>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 py-2 border border-slate-600 rounded-lg text-slate-300 hover:bg-slate-800 transition-colors"
              >
                Annuler
              </button>
              <button
                type="submit"
                disabled={create.isPending}
                className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2"
              >
                {create.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Créer
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    idle: 'bg-slate-800 text-slate-400',
    running: 'bg-yellow-900/50 text-yellow-400',
    completed: 'bg-green-900/50 text-green-400',
    error: 'bg-red-900/50 text-red-400',
  }
  const labels: Record<string, string> = {
    idle: 'Nouveau',
    running: 'En cours',
    completed: 'Terminé',
    error: 'Erreur',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[status] ?? styles.idle}`}>
      {labels[status] ?? status}
    </span>
  )
}

export default function ProjectsPage() {
  const [showModal, setShowModal] = useState(false)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { user, logout } = useAuth()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: api.projects.list,
  })

  const del = useMutation({
    mutationFn: api.projects.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-10">
          <div>
            <h1 className="text-3xl font-bold text-white">WriterAI</h1>
            <p className="text-slate-400 mt-1">Vos romans générés par IA</p>
          </div>
          <div className="flex items-center gap-3">
            {user && <span className="text-sm text-slate-500">{user.email}</span>}
            <button
              onClick={handleLogout}
              title="Déconnexion"
              className="p-2 text-slate-500 hover:text-slate-300 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
            <button
              onClick={() => setShowModal(true)}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              <Plus className="w-5 h-5" />
              Nouveau projet
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-slate-500" />
          </div>
        ) : !projects?.length ? (
          <div className="text-center py-20 text-slate-500">
            <BookOpen className="w-12 h-12 mx-auto mb-4 opacity-40" />
            <p>Aucun projet. Commencez par en créer un !</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {projects.map(p => (
              <div
                key={p.id}
                className="bg-slate-900 border border-slate-800 hover:border-slate-600 rounded-xl p-5 cursor-pointer transition-colors group"
                onClick={() => navigate(`/projects/${p.id}`)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h2 className="text-lg font-semibold text-white truncate">{p.name}</h2>
                    <div className="flex items-center gap-3 mt-1">
                      <StatusBadge status={p.status} />
                      {p.chapters_done > 0 && (
                        <>
                          <span className="text-slate-700">·</span>
                          <span className="text-sm text-slate-500">
                            {p.chapters_done}/{p.chapter_count} chapitres
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); del.mutate(p.id) }}
                    className="opacity-0 group-hover:opacity-100 p-2 text-slate-600 hover:text-red-400 transition-all"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showModal && <NewProjectModal onClose={() => setShowModal(false)} />}
    </div>
  )
}
