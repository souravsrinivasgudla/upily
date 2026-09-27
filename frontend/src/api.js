import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })
// Refresh + AI analysis can take a while on a cold server
const apiSlow = axios.create({ baseURL: '/api', timeout: 90000 })

export const fetchHealth     = ()             => api.get('/health', { validateStatus: s => s < 600 }).then(r => r.data)
export const fetchNews       = (params = {})  => api.get('/news', { params }).then(r => r.data)
export const fetchArticle    = (id)           => api.get(`/news/${id}`).then(r => r.data)
export const analyzeArticle  = (id)           => apiSlow.post(`/news/${id}/analyze`).then(r => r.data)
export const refreshCategory = (category)     => apiSlow.post(`/news/refresh/${category}`).then(r => r.data)
export const fetchTrending   = (force = false) => api.get('/trending', { params: force ? { force: true } : {} }).then(r => r.data)

/** history: [{ role: 'user' | 'assistant', content }] — the last few turns give the AI context */
export const sendChat = (question, { articleId = null, history = [] } = {}) =>
  apiSlow.post('/chat', {
    question,
    article_id: articleId == null ? null : Number(articleId),
    history: history.slice(-8),
  }).then(r => r.data)

/** Human-readable message for any request failure. */
export function errorMessage(err, fallback = 'Something went wrong.') {
  if (!err) return fallback
  if (err.code === 'ECONNABORTED') return 'The server took too long to respond. It may be waking up — try again in a moment.'
  if (!err.response) return 'Cannot reach the Upily server. Check your connection or try again shortly.'

  const { status, data } = err.response
  const detail = typeof data?.detail === 'string' ? data.detail : null
  if (detail) return detail
  if (status === 404) return 'Not found.'
  if (status === 429) return 'Too many requests — please wait a moment.'
  if (status >= 500)  return 'The server had a problem. Please try again shortly.'
  return fallback
}

export default api
