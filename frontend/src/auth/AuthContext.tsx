import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getAccessToken, setAccessToken, setOnUnauthenticated, type UserResponse } from '../api/client'

interface AuthState {
  user: UserResponse | null
  loading: boolean
  setUser: (user: UserResponse | null) => void
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState>({ user: null, loading: true, setUser: () => {}, logout: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    setOnUnauthenticated(() => {
      setUser(null)
      navigate('/login')
    })
    // Si on a un token en localStorage, tenter de récupérer le profil
    if (getAccessToken()) {
      api.auth.me()
        .then(setUser)
        .catch(() => setAccessToken(null))
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  async function logout() {
    await api.auth.logout()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, setUser, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
