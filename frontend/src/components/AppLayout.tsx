import { useNavigate } from 'react-router-dom'
import { LogOut, User } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'

interface AppLayoutProps {
  children: React.ReactNode
}

export default function AppLayout({ children }: AppLayoutProps) {
  const navigate = useNavigate()
  const { user, logout } = useAuth()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between flex-shrink-0">
        <button
          onClick={() => navigate('/')}
          className="text-white font-semibold text-lg hover:text-indigo-400 transition-colors"
        >
          WriterAI
        </button>
        <div className="flex items-center gap-3">
          {user && <span className="text-sm text-slate-500 hidden sm:block">{user.email}</span>}
          <button
            onClick={() => navigate('/account')}
            title="Mon compte"
            className="p-2 text-slate-500 hover:text-slate-300 transition-colors"
          >
            <User className="w-4 h-4" />
          </button>
          <button
            onClick={handleLogout}
            title="Déconnexion"
            className="p-2 text-slate-500 hover:text-slate-300 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>
      <main className="flex-1">
        {children}
      </main>
    </div>
  )
}
