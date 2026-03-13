import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, BookOpen, Trash2, Loader2, LogOut, ChevronRight, ChevronLeft, Settings } from 'lucide-react'
import { api, type ProjectCreateRequest, type LLMConfig } from '../api/client'
import { useAuth } from '../auth/AuthContext'

// --- Wizard de création de projet (3 étapes) ---

type Step = 'general' | 'llm' | 'advanced'
const STEPS: Step[] = ['general', 'llm', 'advanced']
const STEP_LABELS: Record<Step, string> = {
  general: 'Général',
  llm: 'Modèle IA',
  advanced: 'Avancé',
}

interface FormState {
  // Général
  name: string
  source_text: string
  writing_style: string
  tone_keywords: string       // CSV libre
  target_chapter_count: string
  // LLM
  llm_provider: 'ollama' | 'openai' | 'anthropic' | 'other'
  llm_model: string
  llm_api_key: string
  llm_api_base: string
  llm_thinking: 'off' | 'low' | 'medium' | 'high'
  // Avancé
  min_validation_score: string
  max_revision_attempts: string
}

// En Docker, Ollama tourne sur l'hôte → host.docker.internal ; en local → localhost
const OLLAMA_HOST = window.location.hostname === 'localhost' ? 'localhost' : 'host.docker.internal'

const PROVIDER_DEFAULTS: Record<string, { model: string; api_base: string }> = {
  ollama:    { model: 'gpt-oss:20b',         api_base: `http://${OLLAMA_HOST}:11434` },
  openai:    { model: 'gpt-4o',              api_base: '' },
  anthropic: { model: 'claude-opus-4-6', api_base: '' },
  other:     { model: '',                    api_base: '' },
}

const DEFAULTS: FormState = {
  name: '',
  source_text: '',
  writing_style: '',
  tone_keywords: '',
  target_chapter_count: '',
  llm_provider: 'ollama',
  llm_model: 'gpt-oss:20b',
  llm_api_key: '',
  llm_api_base: `http://${OLLAMA_HOST}:11434`,
  llm_thinking: 'high',
  min_validation_score: '7',
  max_revision_attempts: '5',
}

function StepIndicator({ current }: { current: Step }) {
  return (
    <div className="flex items-center gap-2 mb-6">
      {STEPS.map((step, i) => (
        <div key={step} className="flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold transition-colors ${
            step === current
              ? 'bg-indigo-600 text-white'
              : STEPS.indexOf(current) > i
                ? 'bg-green-700 text-white'
                : 'bg-slate-700 text-slate-400'
          }`}>
            {STEPS.indexOf(current) > i ? '✓' : i + 1}
          </div>
          <span className={`text-xs transition-colors ${step === current ? 'text-white' : 'text-slate-500'}`}>
            {STEP_LABELS[step]}
          </span>
          {i < STEPS.length - 1 && <div className="w-6 h-px bg-slate-700" />}
        </div>
      ))}
    </div>
  )
}

function NewProjectModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('general')
  const [form, setForm] = useState<FormState>(DEFAULTS)
  const f = <K extends keyof FormState>(key: K) => (
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm(prev => ({ ...prev, [key]: e.target.value }))
  )

  const create = useMutation({
    mutationFn: (data: ProjectCreateRequest) => api.projects.create(data),
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${project.id}`)
    },
  })

  function canAdvance(): boolean {
    if (step === 'general') return form.name.trim().length > 0 && form.source_text.trim().length >= 10
    if (step === 'llm') return form.llm_model.trim().length > 0
    return true
  }

  function handleProviderChange(provider: FormState['llm_provider']) {
    const def = PROVIDER_DEFAULTS[provider]
    setForm(prev => ({
      ...prev,
      llm_provider: provider,
      llm_model: def.model,
      llm_api_base: def.api_base,
      // Réinitialise thinking si le provider ne le supporte pas
      llm_thinking: provider === 'ollama' || provider === 'anthropic' ? prev.llm_thinking : 'off',
    }))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (step !== 'advanced') { setStep(STEPS[STEPS.indexOf(step) + 1]); return }

    const llm: LLMConfig = {
      provider: form.llm_provider,
      model: form.llm_model.trim(),
    }
    if (form.llm_api_key.trim()) llm.api_key = form.llm_api_key.trim()
    if (form.llm_api_base.trim()) llm.api_base = form.llm_api_base.trim()
    if (form.llm_thinking !== 'off') llm.thinking = form.llm_thinking

    const payload: ProjectCreateRequest = {
      name: form.name.trim(),
      source_text: form.source_text.trim(),
      llm,
    }
    if (form.writing_style.trim()) payload.writing_style = form.writing_style.trim()
    if (form.tone_keywords.trim()) {
      payload.tone_keywords = form.tone_keywords.split(',').map(s => s.trim()).filter(Boolean)
    }
    if (form.target_chapter_count) payload.target_chapter_count = Number(form.target_chapter_count)
    if (form.min_validation_score) payload.min_validation_score = Number(form.min_validation_score)
    if (form.max_revision_attempts) payload.max_revision_attempts = Number(form.max_revision_attempts)

    create.mutate(payload)
  }

  const inputCls = "w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 text-sm"
  const labelCls = "block text-xs font-medium text-slate-400 mb-1"

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-xl max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xl font-bold text-white">Nouveau projet</h2>
            <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">✕</button>
          </div>

          <StepIndicator current={step} />

          <form onSubmit={handleSubmit} noValidate className="space-y-4">

            {/* Étape 1 : Général */}
            {step === 'general' && (
              <>
                <div>
                  <label className={labelCls}>Titre du roman *</label>
                  <input
                    className={inputCls}
                    placeholder="L'oiseau rouge..."
                    value={form.name}
                    onChange={f('name')}
                    required
                    autoFocus
                  />
                </div>

                <div>
                  <label className={labelCls}>Synopsis / Pitch *</label>
                  <textarea
                    rows={6}
                    className={inputCls + ' resize-none'}
                    placeholder="Décrivez votre histoire : personnages principaux, univers, enjeux, ton général. Plus c'est détaillé, meilleur sera le résultat..."
                    value={form.source_text}
                    onChange={f('source_text')}
                    required
                    minLength={10}
                  />
                  <p className="text-xs text-slate-600 mt-1">{form.source_text.length} caractères{form.source_text.length < 200 ? ' — un synopsis de 200+ caractères donnera de meilleurs résultats' : ''}</p>
                </div>

                <div>
                  <label className={labelCls}>Style d'écriture <span className="text-slate-600">(optionnel)</span></label>
                  <input
                    className={inputCls}
                    placeholder="Immersif, poétique, dialogues vifs, phrases courtes..."
                    value={form.writing_style}
                    onChange={f('writing_style')}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Mots-clés de ton <span className="text-slate-600">(CSV)</span></label>
                    <input
                      className={inputCls}
                      placeholder="sombre, épique, mélancolique"
                      value={form.tone_keywords}
                      onChange={f('tone_keywords')}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>Nombre de chapitres <span className="text-slate-600">(optionnel)</span></label>
                    <input
                      type="number"
                      min={2}
                      max={50}
                      className={inputCls}
                      placeholder="Libre (IA décide)"
                      value={form.target_chapter_count}
                      onChange={f('target_chapter_count')}
                    />
                  </div>
                </div>
              </>
            )}

            {/* Étape 2 : LLM */}
            {step === 'llm' && (
              <>
                <div>
                  <label className={labelCls}>Fournisseur</label>
                  <select
                    className={inputCls}
                    value={form.llm_provider}
                    onChange={e => handleProviderChange(e.target.value as FormState['llm_provider'])}
                  >
                    <option value="ollama">Ollama (local)</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="other">Autre (LiteLLM)</option>
                  </select>
                </div>

                <div>
                  <label className={labelCls}>Modèle *</label>
                  <input
                    className={inputCls}
                    placeholder={PROVIDER_DEFAULTS[form.llm_provider].model || 'nom-du-modèle'}
                    value={form.llm_model}
                    onChange={f('llm_model')}
                    required
                  />
                </div>

                {form.llm_provider !== 'ollama' && (
                  <div>
                    <label className={labelCls}>Clé API</label>
                    <input
                      type="password"
                      className={inputCls}
                      placeholder="sk-..."
                      value={form.llm_api_key}
                      onChange={f('llm_api_key')}
                    />
                  </div>
                )}

                <div>
                  <label className={labelCls}>URL de l'API <span className="text-slate-600">(optionnel)</span></label>
                  <input
                    className={inputCls}
                    placeholder={PROVIDER_DEFAULTS[form.llm_provider].api_base || 'https://...'}
                    value={form.llm_api_base}
                    onChange={f('llm_api_base')}
                  />
                </div>

                {(form.llm_provider === 'ollama' || form.llm_provider === 'anthropic') && (
                  <div>
                    <label className={labelCls}>Mode de réflexion (thinking)</label>
                    <select
                      className={inputCls}
                      value={form.llm_thinking}
                      onChange={e => setForm(prev => ({ ...prev, llm_thinking: e.target.value as FormState['llm_thinking'] }))}
                    >
                      <option value="off">Désactivé</option>
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High (recommandé)</option>
                    </select>
                    <p className="text-xs text-slate-600 mt-1">Le thinking améliore la qualité mais augmente la durée de génération</p>
                  </div>
                )}

                <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 text-xs text-slate-500 space-y-1">
                  <p className="font-medium text-slate-400">Résumé</p>
                  <p>{form.llm_provider} · {form.llm_model || '—'}{form.llm_thinking !== 'off' ? ` · thinking=${form.llm_thinking}` : ''}</p>
                  {form.llm_api_base && <p className="truncate">{form.llm_api_base}</p>}
                </div>
              </>
            )}

            {/* Étape 3 : Avancé */}
            {step === 'advanced' && (
              <>
                <div className="flex items-center gap-2 text-slate-400 mb-2">
                  <Settings className="w-4 h-4" />
                  <span className="text-sm">Paramètres de qualité</span>
                </div>

                <div>
                  <label className={labelCls}>Score minimum de validation <span className="text-slate-500">(0-10)</span></label>
                  <input
                    type="number"
                    min={0}
                    max={10}
                    step={0.5}
                    className={inputCls}
                    value={form.min_validation_score}
                    onChange={f('min_validation_score')}
                  />
                  <p className="text-xs text-slate-600 mt-1">En dessous de ce score, le chapitre est révisé. 7 = bon équilibre qualité/vitesse.</p>
                </div>

                <div>
                  <label className={labelCls}>Nombre max de révisions par chapitre</label>
                  <input
                    type="number"
                    min={0}
                    max={10}
                    className={inputCls}
                    value={form.max_revision_attempts}
                    onChange={f('max_revision_attempts')}
                  />
                  <p className="text-xs text-slate-600 mt-1">Au-delà, le chapitre est accepté tel quel. 0 = pas de révision.</p>
                </div>

                <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 text-xs text-slate-500 space-y-1 mt-2">
                  <p className="font-medium text-slate-400">Récapitulatif du projet</p>
                  <p><span className="text-slate-400">Titre :</span> {form.name}</p>
                  <p><span className="text-slate-400">Modèle :</span> {form.llm_provider} / {form.llm_model}</p>
                  {form.target_chapter_count && <p><span className="text-slate-400">Chapitres :</span> {form.target_chapter_count}</p>}
                  {form.writing_style && <p><span className="text-slate-400">Style :</span> {form.writing_style}</p>}
                </div>
              </>
            )}

            {create.error && (
              <p className="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
                {(create.error as Error).message}
              </p>
            )}

            {/* Navigation */}
            <div className="flex gap-3 pt-2">
              {step !== 'general' ? (
                <button
                  type="button"
                  onClick={() => setStep(STEPS[STEPS.indexOf(step) - 1])}
                  className="flex items-center gap-1 px-4 py-2 border border-slate-600 rounded-lg text-slate-300 hover:bg-slate-800 transition-colors text-sm"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Retour
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 border border-slate-600 rounded-lg text-slate-300 hover:bg-slate-800 transition-colors text-sm"
                >
                  Annuler
                </button>
              )}

              <button
                type="submit"
                disabled={!canAdvance() || create.isPending}
                className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2 text-sm"
              >
                {create.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                {step === 'advanced'
                  ? (create.isPending ? 'Création…' : 'Créer le projet')
                  : (<><span>Suivant</span><ChevronRight className="w-4 h-4" /></>)
                }
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

// --- Badge statut ---

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    idle: 'bg-slate-800 text-slate-400',
    running: 'bg-yellow-900/50 text-yellow-400',
    stopping: 'bg-orange-900/50 text-orange-400',
    completed: 'bg-green-900/50 text-green-400',
    error: 'bg-red-900/50 text-red-400',
  }
  const labels: Record<string, string> = {
    idle: 'Nouveau',
    running: 'En cours',
    stopping: 'Arrêt…',
    completed: 'Terminé',
    error: 'Erreur',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[status] ?? styles.idle}`}>
      {labels[status] ?? status}
    </span>
  )
}

// --- Page principale ---

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
                      {p.chapter_count > 0 && (
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
                    className="opacity-0 group-hover:opacity-100 p-2 text-slate-600 hover:text-red-400 transition-all ml-2 flex-shrink-0"
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
