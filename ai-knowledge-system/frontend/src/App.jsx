import { Routes, Route } from 'react-router-dom'
import Layout      from './components/Layout'
import Dashboard   from './pages/Dashboard'
import ArticlePage from './pages/ArticlePage'
import ChatPage    from './pages/ChatPage'
import TrendingPage from './pages/TrendingPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/"            element={<Dashboard />} />
        <Route path="/article/:id" element={<ArticlePage />} />
        <Route path="/chat"        element={<ChatPage />} />
        <Route path="/trending"    element={<TrendingPage />} />
      </Routes>
    </Layout>
  )
}
