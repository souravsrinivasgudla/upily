import { Route, Routes, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import Dashboard from './pages/Dashboard'
import ArticlePage from './pages/ArticlePage'
import ChatPage from './pages/ChatPage'
import TrendingPage from './pages/TrendingPage'
import NotFound from './pages/NotFound'

export default function App() {
  const { pathname } = useLocation()
  return (
    <Layout>
      <ErrorBoundary resetKey={pathname}>
        <Routes>
          <Route path="/"            element={<Dashboard />} />
          <Route path="/article/:id" element={<ArticlePage />} />
          <Route path="/chat"        element={<ChatPage />} />
          <Route path="/trending"    element={<TrendingPage />} />
          <Route path="*"            element={<NotFound />} />
        </Routes>
      </ErrorBoundary>
    </Layout>
  )
}
