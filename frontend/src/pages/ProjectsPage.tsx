import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, BookOpen, Trash2, Loader2, ChevronRight, ChevronLeft, Settings } from 'lucide-react'
import { api, type ProjectCreateRequest, type LLMConfig, type ApiKeyResponse } from '../api/client'
import AppLayout from '../components/AppLayout'

// --- Wizard de création de projet (3 étapes) ---

type Step = 'llm' | 'general' | 'advanced'
const STEPS: Step[] = ['llm', 'general', 'advanced']
const STEP_LABELS: Record<Step, string> = {
  llm: 'Modèle IA',
  general: 'Général',
  advanced: 'Avancé',
}

interface FormState {
  // Général
  name: string
  source_text: string
  writing_style: string
  tone_keywords: string       // CSV libre
  target_chapter_count: string
  // LLM — source = 'local' | api_key id
  llm_source: string          // 'local' ou l'id d'une ApiKey
  llm_model: string
  llm_api_base: string
  llm_thinking: 'off' | 'low' | 'medium' | 'high'
  // Avancé
  min_validation_score: string
  max_revision_attempts: string
}

// En Docker, Ollama tourne sur l'hôte → host.docker.internal ; en local → localhost
const OLLAMA_HOST = window.location.hostname === 'localhost' ? 'localhost' : 'host.docker.internal'


const DEFAULTS: FormState = {
  name: '',
  source_text: '',
  writing_style: '',
  tone_keywords: '',
  target_chapter_count: '',
  llm_source: 'local',
  llm_model: '',
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
  const [step, setStep] = useState<Step>('llm')
  const [form, setForm] = useState<FormState>(DEFAULTS)
  const [customModel, setCustomModel] = useState(false)  // true = afficher l'input libre
  const f = <K extends keyof FormState>(key: K) => (
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm(prev => ({ ...prev, [key]: e.target.value }))
  )

  const { data: apiKeys = [] } = useQuery<ApiKeyResponse[]>({
    queryKey: ['api-keys'],
    queryFn: () => api.account.listApiKeys(),
  })

  // Source sélectionnée : 'local' ou une ApiKey
  const selectedKey = apiKeys.find(k => k.id === form.llm_source)
  const isLocal = form.llm_source === 'local'
  const currentProvider = isLocal ? 'ollama' : (selectedKey?.provider ?? 'other')
  const supportsThinking = currentProvider === 'ollama' || currentProvider === 'anthropic'

  // Chargement des modèles disponibles pour la source sélectionnée
  const { data: modelsData, isFetching: modelsLoading } = useQuery({
    queryKey: ['models', form.llm_source],
    queryFn: () => api.models.list(form.llm_source),
    staleTime: 30_000,
  })
  const availableModels = modelsData?.models ?? []

  const create = useMutation({
    mutationFn: (data: ProjectCreateRequest) => api.projects.create(data),
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${project.id}`)
    },
  })

  function handleSourceChange(source: string) {
    const key = apiKeys.find(k => k.id === source)
    const provider = source === 'local' ? 'ollama' : (key?.provider ?? 'other')
    setForm(prev => ({
      ...prev,
      llm_source: source,
      llm_model: '',
      llm_api_base: source === 'local' ? `http://${OLLAMA_HOST}:11434` : '',
      llm_thinking: provider === 'ollama' || provider === 'anthropic' ? prev.llm_thinking : 'off',
    }))
    setCustomModel(false)
  }

  function handleModelSelect(value: string) {
    if (value === '__other__') {
      setCustomModel(true)
      setForm(prev => ({ ...prev, llm_model: '' }))
    } else {
      setCustomModel(false)
      setForm(prev => ({ ...prev, llm_model: value }))
    }
  }

  function canAdvance(): boolean {
    if (step === 'llm') return form.llm_model.trim().length > 0
    if (step === 'general') return form.name.trim().length > 0 && form.source_text.trim().length >= 10
    return true
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (step !== 'advanced') { setStep(STEPS[STEPS.indexOf(step) + 1]); return }

    const llm: LLMConfig = {
      provider: currentProvider,
      model: form.llm_model.trim(),
    }
    if (isLocal) {
      if (form.llm_api_base.trim()) llm.api_base = form.llm_api_base.trim()
    } else if (selectedKey) {
      llm.api_key_id = selectedKey.id
    }
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

            {/* Étape 1 : Modèle IA */}
            {step === 'llm' && (
              <>
                <div>
                  <label className={labelCls}>Source</label>
                  <select
                    className={inputCls}
                    value={form.llm_source}
                    onChange={e => handleSourceChange(e.target.value)}
                  >
                    <option value="local">Local (Ollama)</option>
                    {apiKeys.length > 0 && (
                      <optgroup label="Mes clés API">
                        {apiKeys.map(k => (
                          <option key={k.id} value={k.id}>{k.label} ({k.provider})</option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  {apiKeys.length === 0 && (
                    <p className="text-xs text-slate-600 mt-1">
                      Aucune clé API enregistrée.{' '}
                      <button type="button" onClick={() => { onClose(); navigate('/account') }} className="text-indigo-400 hover:text-indigo-300">
                        Ajouter dans Mon compte →
                      </button>
                    </p>
                  )}
                </div>

                <div>
                  <label className={labelCls}>
                    Modèle *
                    {modelsLoading && <span className="text-slate-600 font-normal ml-2">Chargement…</span>}
                  </label>

                  {!customModel ? (
                    <select
                      className={inputCls}
                      value={form.llm_model}
                      onChange={e => handleModelSelect(e.target.value)}
                      disabled={modelsLoading}
                    >
                      <option value="">— Choisir un modèle —</option>
                      {availableModels.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                      <option value="__other__">Autre (saisir manuellement)</option>
                    </select>
                  ) : (
                    <div className="flex gap-2">
                      <input
                        className={inputCls}
                        placeholder="nom-du-modèle"
                        value={form.llm_model}
                        onChange={f('llm_model')}
                        autoFocus
                      />
                      <button
                        type="button"
                        onClick={() => { setCustomModel(false); setForm(prev => ({ ...prev, llm_model: '' })) }}
                        className="text-xs text-slate-500 hover:text-slate-300 whitespace-nowrap"
                      >
                        ← Liste
                      </button>
                    </div>
                  )}

                  {availableModels.length === 0 && !modelsLoading && isLocal && (
                    <p className="text-xs text-amber-600 mt-1">Ollama inaccessible ou aucun modèle installé.</p>
                  )}
                </div>

                {supportsThinking && (
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
                  <p>
                    {isLocal ? 'Ollama (local)' : selectedKey?.label ?? '—'} · {form.llm_model || '—'}
                    {form.llm_thinking !== 'off' ? ` · thinking=${form.llm_thinking}` : ''}
                  </p>
                </div>
              </>
            )}

            {/* Étape 2 : Général */}
            {step === 'general' && (
              <>
                <div>
                  <label className={labelCls}>Titre du roman *</label>
                  <input
                    className={inputCls}
                    placeholder="L'oiseau rouge..."
                    value={form.name}
                    onChange={f('name')}
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
                  <p>
                    <span className="text-slate-400">Modèle :</span>{' '}
                    {isLocal ? 'Ollama (local)' : selectedKey?.label ?? '—'} / {form.llm_model}
                  </p>
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
              {step !== 'llm' ? (
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

  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: api.projects.list,
  })

  const del = useMutation({
    mutationFn: api.projects.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

  return (
    <AppLayout>
      <div className="p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-10">
          <div>
            <p className="text-slate-400">Vos romans générés par IA</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg font-medium transition-colors"
          >
            <Plus className="w-5 h-5" />
            Nouveau projet
          </button>
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
      </div>

      {showModal && <NewProjectModal onClose={() => setShowModal(false)} />}
    </AppLayout>
  )
}
