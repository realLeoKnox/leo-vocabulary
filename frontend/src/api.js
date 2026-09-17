const base = '/api'

async function request(path, options = {}) {
  const response = await fetch(base + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = Array.isArray(body.detail) ? body.detail.map(x => `${x.loc?.join('.')}: ${x.msg}`).join('\n') : body.detail
    throw new Error(detail || `请求失败 (${response.status})`)
  }
  return response.status === 204 ? null : response.json()
}

export const api = {
  dashboard: () => request('/dashboard'),
  words: (q = '') => request(`/words?q=${encodeURIComponent(q)}`),
  createWord: data => request('/words', { method: 'POST', body: JSON.stringify(data) }),
  updateWord: (id, data) => request(`/words/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteWord: id => request(`/words/${id}`, { method: 'DELETE' }),
  sources: () => request('/sources'),
  createSource: data => request('/sources', { method: 'POST', body: JSON.stringify(data) }),
  deleteSource: id => request(`/sources/${id}`, { method: 'DELETE' }),
  previewImport: data => request('/import/preview', { method: 'POST', body: JSON.stringify(data) }),
  runImport: data => request('/import', { method: 'POST', body: JSON.stringify(data) }),
  reviewQueue: mode => request(`/review/queue?mode=${mode}`),
  answer: data => request('/review/answer', { method: 'POST', body: JSON.stringify(data) }),
}

