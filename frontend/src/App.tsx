import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/useAuthStore'
import { RequireAuth } from './components/RequireAuth'
import { AppShell } from './components/AppShell'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { Step1 } from './pages/Step1'
import { RunDetail } from './pages/RunDetail'
import { Review } from './pages/Review'
import { Step2 } from './pages/Step2'
import { Publish } from './pages/Publish'
import { Runs } from './pages/Runs'
import { Toolbox } from './pages/Toolbox'
import { Settings } from './pages/Settings'

export default function App() {
  const fetchMe = useAuthStore((s) => s.fetchMe)
  useEffect(() => {
    fetchMe()
  }, [fetchMe])

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="step1" element={<Step1 />} />
        <Route path="runs/:runId" element={<RunDetail />} />
        <Route path="review" element={<Review />} />
        <Route path="step2" element={<Step2 />} />
        <Route path="publish" element={<Publish />} />
        <Route path="toolbox" element={<Toolbox />} />
        <Route path="runs" element={<Runs />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
