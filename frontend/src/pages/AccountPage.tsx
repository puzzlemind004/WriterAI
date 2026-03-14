import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type ApiKeyResponse } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import AppLayout from '../components/AppLayout'

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'mistral', label: 'Mistral' },
  { value: 'cohere', label: 'Cohere' },
  { value: 'other', label: 'Autre' },
]

export default function AccountPage() {
  const { user } = useAuth()
  const qc = useQueryClient()

  // --- Mot de passe ---
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [pwdError, setPwdError] = useState<string | null>(null)
  const [pwdSuccess, setPwdSuccess] = useState(false)
  const [pwdLoading, setPwdLoading] = useState(false)

  // --- Nouvelle clé API ---
  const [newKeyLabel, setNewKeyLabel] = useState('')
  const [newKeyProvider, setNewKeyProvider] = useState('openai')
  const [newKeyValue, setNewKeyValue] = useState('')
  const [keyError, setKeyError] = useState<string | null>(null)

  const { data: apiKeys = [], isLoading: keysLoading } = useQuery<ApiKeyResponse[]>({
    queryKey: ['api-keys'],
    queryFn: () => api.account.listApiKeys(),
  })

  const createKey = useMutation({
    mutationFn: () => api.account.createApiKey(newKeyLabel, newKeyProvider, newKeyValue),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      setNewKeyLabel('')
      setNewKeyValue('')
      setNewKeyProvider('openai')
      setKeyError(null)
    },
    onError: (e: Error) => setKeyError(e.message),
  })

  const deleteKey = useMutation({
    mutationFn: (id: string) => api.account.deleteApiKey(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
  })

  async function handlePasswordChange(e: React.FormEvent) {
    e.preventDefault()
    setPwdError(null)
    setPwdSuccess(false)
    if (newPwd.length < 8) {
      setPwdError('Le nouveau mot de passe doit faire au moins 8 caractères')
      return
    }
    setPwdLoading(true)
    try {
      await api.account.changePassword(currentPwd, newPwd)
      setPwdSuccess(true)
      setCurrentPwd('')
      setNewPwd('')
    } catch (e) {
      setPwdError(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setPwdLoading(false)
    }
  }

  function handleCreateKey(e: React.FormEvent) {
    e.preventDefault()
    setKeyError(null)
    if (!newKeyLabel.trim() || !newKeyValue.trim()) {
      setKeyError('Label et valeur de clé requis')
      return
    }
    createKey.mutate()
  }

  const providerLabel = (p: string) => PROVIDERS.find(x => x.value === p)?.label ?? p

  return (
    <AppLayout>
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-10">

        {/* Section : Informations */}
        <section>
          <h2 className="text-base font-semibold text-gray-300 mb-4">Informations</h2>
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Email</span>
              <span>{user?.email ?? '—'}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Compte créé le</span>
              <span>
                {user?.created_at
                  ? new Date(user.created_at).toLocaleDateString('fr-FR', {
                      day: '2-digit', month: 'long', year: 'numeric',
                    })
                  : '—'}
              </span>
            </div>
          </div>
        </section>

        {/* Section : Mot de passe */}
        <section>
          <h2 className="text-base font-semibold text-gray-300 mb-4">Changer le mot de passe</h2>
          <form
            onSubmit={handlePasswordChange}
            noValidate
            className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4"
          >
            <div>
              <label className="block text-sm text-gray-400 mb-1">Mot de passe actuel</label>
              <input
                type="password"
                value={currentPwd}
                onChange={e => setCurrentPwd(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                placeholder="••••••••"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Nouveau mot de passe</label>
              <input
                type="password"
                value={newPwd}
                onChange={e => setNewPwd(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                placeholder="8 caractères minimum"
              />
            </div>
            {pwdError && <p className="text-red-400 text-sm">{pwdError}</p>}
            {pwdSuccess && <p className="text-green-400 text-sm">Mot de passe mis à jour !</p>}
            <button
              type="submit"
              disabled={pwdLoading}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              {pwdLoading ? 'Mise à jour…' : 'Mettre à jour'}
            </button>
          </form>
        </section>

        {/* Section : Clés API */}
        <section>
          <h2 className="text-base font-semibold text-gray-300 mb-4">Clés API</h2>

          {/* Ajouter une clé */}
          <form
            onSubmit={handleCreateKey}
            noValidate
            className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4 mb-4"
          >
            <p className="text-sm text-gray-400">Ajouter une clé</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Label</label>
                <input
                  type="text"
                  value={newKeyLabel}
                  onChange={e => setNewKeyLabel(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                  placeholder="Mon projet OpenAI"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Fournisseur</label>
                <select
                  value={newKeyProvider}
                  onChange={e => setNewKeyProvider(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                >
                  {PROVIDERS.map(p => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Valeur de la clé</label>
              <input
                type="password"
                value={newKeyValue}
                onChange={e => setNewKeyValue(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                placeholder="sk-..."
                autoComplete="off"
              />
            </div>
            {keyError && <p className="text-red-400 text-sm">{keyError}</p>}
            <button
              type="submit"
              disabled={createKey.isPending}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              {createKey.isPending ? 'Ajout…' : 'Ajouter la clé'}
            </button>
          </form>

          {/* Liste des clés */}
          {keysLoading ? (
            <p className="text-sm text-gray-500">Chargement…</p>
          ) : apiKeys.length === 0 ? (
            <p className="text-sm text-gray-500">Aucune clé enregistrée.</p>
          ) : (
            <div className="space-y-2">
              {apiKeys.map(k => (
                <div
                  key={k.id}
                  className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl px-4 py-3"
                >
                  <div className="space-y-0.5">
                    <p className="text-sm font-medium">{k.label}</p>
                    <p className="text-xs text-gray-500">
                      {providerLabel(k.provider)} · ajoutée le{' '}
                      {new Date(k.created_at).toLocaleDateString('fr-FR')}
                    </p>
                  </div>
                  <button
                    onClick={() => deleteKey.mutate(k.id)}
                    disabled={deleteKey.isPending}
                    className="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
                  >
                    Supprimer
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </AppLayout>
  )
}
