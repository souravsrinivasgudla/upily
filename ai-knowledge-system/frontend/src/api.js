import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// Separate instance with longer timeout for refresh (pipeline can take ~60s)
const apiSlow = axios.create({ baseURL: '/api', timeout: 120000 })

export const fetchNews        = (params = {}) => api.get('/news', { params }).then(r => r.data)
export const fetchArticle     = (id)          => api.get(`/news/${id}`).then(r => r.data)
export const refreshCategory  = (category)    => apiSlow.post(`/news/refresh/${category}`).then(r => r.data)
export const fetchTrending    = ()            => api.get('/trending').then(r => r.data)
export const summarizeArticle = (title, content) => api.post('/ai/summarize', { title, content }).then(r => r.data)
export const enrichArticle    = (id, data)    => api.patch(`/news/${id}/enrich`, data).then(r => r.data)
export const sendChat         = (question, article_id = null, article_data = null) =>
  api.post('/chat', { question, article_id: String(article_id), article_data }).then(r => r.data)

export default api
