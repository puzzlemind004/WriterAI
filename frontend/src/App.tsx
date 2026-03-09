import { Routes, Route } from 'react-router-dom'
import ProjectsPage from './pages/ProjectsPage'
import ProjectPage from './pages/ProjectPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectsPage />} />
      <Route path="/projects/:id" element={<ProjectPage />} />
    </Routes>
  )
}
